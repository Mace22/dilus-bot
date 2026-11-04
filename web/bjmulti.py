"""Blackjack multijugador del panel: mesas en vivo de hasta 5 personas contra el dealer.

Usa exactamente las mismas reglas y pagos que el blackjack contra la casa (cogs/blackjack.py):
zapato de 6 mazos, el dealer se planta en 17, el blackjack natural paga 3 a 2 y se puede doblar con las dos primeras cartas.

Cómo funciona una mesa:
  1. Alguien abre una mesa (o se sienta en una abierta) y elige su apuesta. La apuesta se descuenta al sentarse
     y se devuelve entera si se va antes de repartir o si la mesa se cierra por inactividad.
  2. Con 2 o más personas sentadas, quien abrió la mesa (el primer asiento) reparte.
  3. Se juega por turnos, de izquierda a derecha. Si alguien no juega a tiempo, se planta solo.
  4. El dealer juega, se pagan todas las manos y la mesa vuelve a quedar abierta para otra ronda.
"""
import asyncio
import logging
import random
import time
from itertools import count
from types import SimpleNamespace

from cogs import blackjack as bj
from web.common import ApiError

log = logging.getLogger("dilus-bot.web")

MAX_SEATS = 5            # jugadores por mesa
MIN_PLAYERS = 2          # para poder repartir
MAX_TABLES = 8           # mesas abiertas a la vez por servidor
TURN_TIME = 45           # segundos para decidir; si no, se planta solo
TURN_GRACE = 1.5         # margen extra por la latencia
LOBBY_IDLE = 300         # mesa esperando sin movimiento: se cierra y se devuelven las apuestas
EMPTY_KEEP = 600         # mesa vacía (con los resultados de la última ronda a la vista): se borra


class Seat:
    __slots__ = ("uid", "name", "avatar", "base_bet", "bet", "cards", "doubled", "done", "outcome", "payout")

    def __init__(self, uid: int, name: str, avatar: str | None, bet: int):
        self.uid = uid
        self.name = name
        self.avatar = avatar
        self.base_bet = bet
        self.bet = bet                    # sube al doblar
        self.cards: list[tuple[str, str]] = []
        self.doubled = False
        self.done = False                 # ya terminó su mano (se plantó, se pasó, llegó a 21 o dobló)
        self.outcome: str | None = None
        self.payout = 0

    @property
    def natural(self) -> bool:
        return bj.is_blackjack(self.cards)


class Table:
    def __init__(self, tid: int, gid: int):
        self.id = tid
        self.gid = gid
        self.status = "lobby"             # lobby (abierta) | playing (repartida)
        self.seats: list[Seat] = []
        self.dealer: list[tuple[str, str]] = []
        self.shoe: list[tuple[str, str]] = []
        self.turn = -1                    # índice del asiento que juega
        self.deadline = 0.0
        self.round = 0
        self.last: dict | None = None     # resultado de la última ronda (para verlo después de que se paga)
        self.v = 1                        # sube con cada cambio: el navegador solo pide lo nuevo
        self.touched = time.time()
        self.closed = False
        self.lock = asyncio.Lock()


class BJMulti:
    def __init__(self, svc):
        self.svc = svc
        self.tables: dict[int, Table] = {}
        self.by_user: dict[tuple[int, int], int] = {}      # (servidor, persona) -> mesa donde está sentada
        self._ids = count(1)
        self._gate = asyncio.Lock()                        # evita que una persona ocupe dos asientos a la vez

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    @property
    def eco(self):
        return self.svc.eco

    @property
    def db(self):
        return self.svc.db

    @staticmethod
    def _check_bet(bet):
        if not isinstance(bet, int) or isinstance(bet, bool) or not bj.MIN_BET <= bet <= bj.MAX_BET:
            raise ApiError(f"La apuesta mínima es {bj.MIN_BET} monedas.")

    def _table(self, gid: int, tid) -> Table:
        if isinstance(tid, bool) or not str(tid).isdigit():
            raise ApiError("Mesa inválida.")
        t = self.tables.get(int(tid))
        if t is None or t.gid != gid or t.closed:
            raise ApiError("Esa mesa ya no existe.", 404)
        return t

    @staticmethod
    def _seat(t: Table, uid: int) -> Seat:
        for s in t.seats:
            if s.uid == uid:
                return s
        raise ApiError("No estás sentado en esta mesa.", 404)

    @staticmethod
    def _touch(t: Table):
        t.v += 1
        t.touched = time.time()

    @staticmethod
    def _cards(cards) -> list:
        return [list(c) for c in cards]

    async def recover(self):
        """Si el bot se reinició con mesas abiertas, devuelve las apuestas que estaban en juego."""
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS web_bj_multi ("
            "guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, bet INTEGER NOT NULL, PRIMARY KEY (guild_id, user_id))"
        )
        rows = await self.db.fetchall("SELECT guild_id, user_id, bet FROM web_bj_multi")
        for r in rows:
            await self.db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", (r["guild_id"], r["user_id"]))
            await self.db.execute(
                "UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (r["bet"], r["guild_id"], r["user_id"])
            )
        if rows:
            await self.db.execute("DELETE FROM web_bj_multi")
            log.info("Web: devolví las apuestas de %d jugador(es) de mesas de blackjack que quedaron abiertas.", len(rows))

    # ------------------------------------------------------------------
    # Serialización (lo que ve el navegador)
    # ------------------------------------------------------------------
    def _seat_dict(self, t: Table, i: int, s: Seat) -> dict:
        v = bj.hand_value(s.cards)
        if s.outcome:
            status = "done"
        elif s.natural:
            status = "blackjack"
        elif v > 21:
            status = "bust"
        elif s.done:
            status = "stand"
        elif t.status == "playing" and t.turn == i:
            status = "turn"
        else:
            status = "wait"
        return {
            "id": str(s.uid), "name": s.name, "avatar": s.avatar,
            "bet": s.bet, "base_bet": s.base_bet, "doubled": s.doubled,
            "cards": self._cards(s.cards), "value": v if s.cards else None,
            "status": status, "outcome": s.outcome,
            "payout": s.payout, "net": (s.payout - s.bet) if s.outcome else None,
        }

    def _dict(self, t: Table, uid: int, balance: int) -> dict:
        playing = t.status == "playing"
        cur = t.seats[t.turn] if playing and 0 <= t.turn < len(t.seats) else None
        mine = next((s for s in t.seats if s.uid == uid), None)
        hide = playing
        dealer = self._cards(t.dealer)
        if hide and len(dealer) > 1:
            dealer[1] = None
        if not t.dealer:
            dealer_value = None
        elif hide:
            dealer_value = bj.card_points(t.dealer[0][0])
        else:
            dealer_value = bj.hand_value(t.dealer)
        my_turn = cur is not None and cur is mine
        return {
            "id": t.id, "v": t.v, "status": t.status, "round": t.round,
            "host": str(t.seats[0].uid) if t.seats else None,
            "seats": [self._seat_dict(t, i, s) for i, s in enumerate(t.seats)],
            "dealer": dealer, "dealer_value": dealer_value, "dealer_hidden": hide and bool(t.dealer),
            "turn": str(cur.uid) if cur else None,
            "turn_left": round(max(0.0, t.deadline - time.time()), 1) if cur else None,
            "turn_time": TURN_TIME,
            "max_seats": MAX_SEATS, "min_players": MIN_PLAYERS,
            "me": {
                "seated": mine is not None, "my_turn": my_turn,
                "can_double": bool(my_turn and len(mine.cards) == 2 and not mine.doubled),
                "bet": mine.bet if mine else 0, "base_bet": mine.base_bet if mine else 0,
            },
            "last": t.last, "balance": balance,
        }

    async def _reply(self, t: Table, uid: int) -> dict:
        balance = await self.eco.balance(t.gid, uid)
        return {"table": self._dict(t, uid, balance), "balance": balance}

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def list(self, gid: int, uid: int) -> dict:
        out = []
        for t in self.tables.values():
            if t.gid != gid or t.closed:
                continue
            out.append({
                "id": t.id, "status": t.status, "round": t.round, "count": len(t.seats), "max": MAX_SEATS,
                "players": [{"id": str(s.uid), "name": s.name, "avatar": s.avatar, "bet": s.bet} for s in t.seats],
            })
        out.sort(key=lambda x: x["id"])
        return {"tables": out, "mine": self.by_user.get((gid, uid)), "max": MAX_SEATS, "balance": await self.eco.balance(gid, uid)}

    async def state(self, gid: int, uid: int, tid, since=None) -> dict:
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            await self._tick(t)
            balance = await self.eco.balance(gid, uid)
            if since is not None and str(since) == str(t.v):
                return {"same": True, "balance": balance}
            return self._dict(t, uid, balance)

    # ------------------------------------------------------------------
    # Sentarse / irse
    # ------------------------------------------------------------------
    async def _sit(self, t: Table, uid: int, bet: int):
        name, avatar = await self.svc.who(self.svc.guild(t.gid), uid)
        if not await self.eco.add(t.gid, uid, -bet):
            raise ApiError("No tenés suficientes monedas para esa apuesta.", 402)
        try:
            await self.db.execute("INSERT OR REPLACE INTO web_bj_multi (guild_id, user_id, bet) VALUES (?, ?, ?)", (t.gid, uid, bet))
        except Exception:
            await self.eco.add(t.gid, uid, bet)
            raise
        t.seats.append(Seat(uid, name, avatar, bet))
        self.by_user[(t.gid, uid)] = t.id
        self._touch(t)

    async def _refund(self, t: Table, s: Seat):
        await self.eco.add(t.gid, s.uid, s.bet)
        await self.db.execute("DELETE FROM web_bj_multi WHERE guild_id = ? AND user_id = ?", (t.gid, s.uid))
        self.by_user.pop((t.gid, s.uid), None)

    async def create(self, gid: int, uid: int, bet) -> dict:
        self._check_bet(bet)
        async with self._gate:
            if (gid, uid) in self.by_user:
                raise ApiError("Ya estás sentado en una mesa. Salí de esa primero.", 409)
            if sum(1 for t in self.tables.values() if t.gid == gid and not t.closed) >= MAX_TABLES:
                raise ApiError("Ya hay muchas mesas abiertas en este servidor. Unite a una.", 409)
            t = Table(next(self._ids), gid)
            await self._sit(t, uid, bet)
            self.tables[t.id] = t
        return await self._reply(t, uid)

    async def join(self, gid: int, uid: int, tid, bet) -> dict:
        self._check_bet(bet)
        t = self._table(gid, tid)
        async with self._gate:
            async with t.lock:
                if t.closed:
                    raise ApiError("Esa mesa ya no existe.", 404)
                if (gid, uid) in self.by_user:
                    raise ApiError("Ya estás sentado en una mesa.", 409)
                if t.status != "lobby":
                    raise ApiError("Esa mesa ya está jugando. Esperá a que termine la ronda.", 409)
                if len(t.seats) >= MAX_SEATS:
                    raise ApiError(f"La mesa está llena (máximo {MAX_SEATS}).", 409)
                await self._sit(t, uid, bet)
        return await self._reply(t, uid)

    async def leave(self, gid: int, uid: int, tid) -> dict:
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            s = self._seat(t, uid)
            if t.status != "lobby":
                raise ApiError("No podés irte en medio de una ronda. Jugá tu mano o esperá a que termine.", 409)
            await self._refund(t, s)
            t.seats.remove(s)
            self._touch(t)
        return {"left": True, "balance": await self.eco.balance(gid, uid)}

    # ------------------------------------------------------------------
    # Ronda
    # ------------------------------------------------------------------
    async def start(self, gid: int, uid: int, tid) -> dict:
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            s = self._seat(t, uid)
            if t.status != "lobby":
                raise ApiError("La ronda ya está en marcha.", 409)
            if t.seats[0] is not s:
                raise ApiError("Solo quien abrió la mesa puede repartir.", 403)
            if len(t.seats) < MIN_PLAYERS:
                raise ApiError(f"Hacen falta al menos {MIN_PLAYERS} jugadores para repartir.", 409)
            t.status = "playing"
            t.round += 1
            t.last = None
            t.shoe = [(r, su) for _ in range(bj.DECKS) for su in bj.SUITS for r in bj.RANKS]
            random.shuffle(t.shoe)
            for seat in t.seats:
                seat.cards = [t.shoe.pop(), t.shoe.pop()]
                seat.done = seat.natural          # el blackjack natural no juega: se cobra al final
                seat.doubled = False
                seat.outcome = None
                seat.payout = 0
            t.dealer = [t.shoe.pop(), t.shoe.pop()]
            self._touch(t)
            if bj.is_blackjack(t.dealer):         # blackjack del dealer: se termina la ronda enseguida
                for seat in t.seats:
                    seat.done = True
            await self._next(t)
        return await self._reply(t, uid)

    async def act(self, gid: int, uid: int, tid, action) -> dict:
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            await self._tick(t)                    # por si su turno ya había vencido
            self._seat(t, uid)
            if t.status != "playing":
                raise ApiError("La ronda ya terminó.", 409)
            if not 0 <= t.turn < len(t.seats) or t.seats[t.turn].uid != uid:
                raise ApiError("Todavía no es tu turno.", 409)
            s = t.seats[t.turn]
            if action == "hit":
                s.cards.append(t.shoe.pop())
                if bj.hand_value(s.cards) >= 21:   # se pasó o llegó a 21: se planta solo
                    s.done = True
            elif action == "stand":
                s.done = True
            elif action == "double":
                if s.doubled or len(s.cards) != 2:
                    raise ApiError("Solo podés doblar con tus dos primeras cartas.", 409)
                if not await self.eco.add(t.gid, uid, -s.base_bet):
                    raise ApiError("No te alcanzan las monedas para doblar.", 402)
                s.bet += s.base_bet
                s.doubled = True
                await self.db.execute("UPDATE web_bj_multi SET bet = ? WHERE guild_id = ? AND user_id = ?", (s.bet, t.gid, uid))
                s.cards.append(t.shoe.pop())       # una sola carta y se planta
                s.done = True
            else:
                raise ApiError("Acción inválida.")
            self._touch(t)
            if s.done:
                await self._next(t)
            else:
                t.deadline = time.time() + TURN_TIME
        return await self._reply(t, uid)

    async def _next(self, t: Table):
        """Pasa el turno a la siguiente mano pendiente; si no queda ninguna, juega el dealer y se paga."""
        for i, s in enumerate(t.seats):
            if not s.done:
                t.turn = i
                t.deadline = time.time() + TURN_TIME
                return
        t.turn = -1
        await self._finish(t)

    async def _tick(self, t: Table):
        """Si el turno actual venció, esa mano se planta sola (igual que en el blackjack contra la casa)."""
        if t.status == "playing" and 0 <= t.turn < len(t.seats) and time.time() > t.deadline + TURN_GRACE:
            t.seats[t.turn].done = True
            self._touch(t)
            await self._next(t)

    async def _finish(self, t: Table):
        dealer_nat = bj.is_blackjack(t.dealer)
        live = [s for s in t.seats if not s.natural and bj.hand_value(s.cards) <= 21]
        if live:                                  # el dealer solo juega si queda alguien sin pasarse
            while bj.hand_value(t.dealer) < 17:
                t.dealer.append(t.shoe.pop())
        for s in t.seats:
            if s.natural:
                s.outcome = "push" if dealer_nat else "blackjack"
            elif dealer_nat:
                s.outcome = "dealer_blackjack"
            else:
                s.outcome = bj.final_outcome(SimpleNamespace(player=s.cards, dealer=t.dealer))
            s.payout = bj.payout_for(s.outcome, s.bet)
            try:
                if s.payout:
                    await self.eco.add(t.gid, s.uid, s.payout)
                await self.db.execute("DELETE FROM web_bj_multi WHERE guild_id = ? AND user_id = ?", (t.gid, s.uid))
                await self.svc.record(t.gid, s.uid, "blackjack", s.bet, s.payout, s.outcome)
            except Exception:
                log.exception("No pude pagar una mano de blackjack multijugador")
            self.by_user.pop((t.gid, s.uid), None)
        t.last = {
            "round": t.round, "dealer": self._cards(t.dealer), "dealer_value": bj.hand_value(t.dealer),
            "seats": [self._seat_dict(t, i, s) for i, s in enumerate(t.seats)],
        }
        t.seats = []
        t.dealer = []
        t.shoe = []
        t.status = "lobby"
        self._touch(t)

    # ------------------------------------------------------------------
    # Limpieza (la llama el barredor cada 30 segundos)
    # ------------------------------------------------------------------
    async def sweep(self):
        now = time.time()
        for t in list(self.tables.values()):
            async with t.lock:
                if t.closed:
                    continue
                try:
                    if t.status == "playing":
                        await self._tick(t)
                    elif t.seats and now - t.touched > LOBBY_IDLE:
                        for s in list(t.seats):    # nadie repartió: se devuelve todo y se cierra
                            await self._refund(t, s)
                        t.seats = []
                        self._drop(t)
                    elif not t.seats and now - t.touched > EMPTY_KEEP:
                        self._drop(t)
                except Exception:
                    log.exception("No pude limpiar una mesa de blackjack")

    def _drop(self, t: Table):
        t.closed = True
        self.tables.pop(t.id, None)
