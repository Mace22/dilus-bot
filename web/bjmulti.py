"""Blackjack multijugador del panel: mesas en vivo de hasta 5 personas contra el dealer.

Usa exactamente las mismas reglas y pagos que el blackjack contra la casa (cogs/blackjack.py):
zapato de 6 mazos, el dealer se planta en 17, el blackjack natural paga 3 a 2 y se puede doblar con las dos primeras cartas.

Cómo funciona una mesa:
  1. Cualquiera abre una mesa o se sienta en una abierta (hasta 5). Sentarse no cuesta nada: se apuesta en cada ronda.
  2. Fase de apuestas: cada uno apuesta su mano. Quien ya apostó también puede apostar por el jugador de su izquierda
     y/o de su derecha (cobra según cómo le vaya a ese jugador). Las apuestas se descuentan al hacerlas y se devuelven
     si se cambian, se retiran, se va de la mesa o la mesa se borra antes de repartir.
  3. Se reparte cuando quien abrió la mesa lo decide, cuando todos los sentados ya apostaron, o cuando se acaba el tiempo
     de apuestas. Quien no apostó se queda sentado mirando esa ronda (tras varias rondas seguidas sin apostar, se lo levanta).
  4. Se juega por turnos, de izquierda a derecha. Si alguien no juega a tiempo, se planta solo.
  5. Juega el dealer, se paga todo y la mesa vuelve a la fase de apuestas con todos todavía sentados.
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
MIN_PLAYERS = 2          # apostadores necesarios para la primera ronda de una mesa nueva
MAX_TABLES = 8           # mesas abiertas a la vez por servidor
TURN_TIME = 45           # segundos para decidir; si no, se planta solo
TURN_GRACE = 1.5         # margen extra por la latencia
BET_TIME = 30            # segundos para apostar entre rondas; después se reparte sin quien no apostó
READY_GRACE = 4          # cuando todos apostaron, se reparte a los pocos segundos
MAX_MISSED = 3           # rondas seguidas sin apostar: se lo levanta de la mesa
LOBBY_IDLE = 300         # mesa nueva sin movimiento: se cierra y se devuelven las apuestas
EMPTY_KEEP = 180         # mesa sin nadie sentado: se borra


class Seat:
    __slots__ = ("uid", "name", "avatar", "bet", "base_bet", "cards", "doubled", "done", "playing",
                 "sides", "result", "side_result", "missed")

    def __init__(self, uid: int, name: str, avatar: str | None):
        self.uid = uid
        self.name = name
        self.avatar = avatar
        self.bet = 0                      # apuesta de esta ronda (0 = todavía no apostó); sube al doblar
        self.base_bet = 0                 # última apuesta hecha (se sugiere para la revancha)
        self.cards: list[tuple[str, str]] = []
        self.doubled = False
        self.done = False                 # ya terminó su mano (se plantó, se pasó, llegó a 21 o dobló)
        self.playing = False              # participa en la ronda repartida
        self.sides: dict[int, int] = {}   # apuestas por vecinos: id del vecino -> monto
        self.result: dict | None = None   # resultado de la última ronda
        self.side_result: list = []       # cómo le fue con sus apuestas por vecinos la última ronda
        self.missed = 0                   # rondas seguidas sin apostar

    @property
    def natural(self) -> bool:
        return bj.is_blackjack(self.cards)

    @property
    def stake(self) -> int:
        """Todo lo que tiene puesto ahora (mano + apuestas por vecinos)."""
        return self.bet + sum(self.sides.values())


class Table:
    def __init__(self, tid: int, gid: int, owner: int):
        self.id = tid
        self.gid = gid
        self.owner = owner                # quien abrió la mesa (puede borrarla)
        self.status = "betting"           # betting (apuestas abiertas) | playing (repartida)
        self.seats: list[Seat] = []
        self.dealer: list[tuple[str, str]] = []
        self.shoe: list[tuple[str, str]] = []
        self.cur: Seat | None = None      # a quién le toca jugar
        self.deadline = 0.0               # fin del turno actual
        self.bet_deadline: float | None = None   # fin del tiempo de apuestas (None: sin límite, mesa que todavía no repartió)
        self.round = 0
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

    @staticmethod
    def _starter(t: Table) -> Seat | None:
        """Quien puede repartir antes de tiempo: quien abrió la mesa (si sigue sentado) o, si no, el primer asiento."""
        for s in t.seats:
            if s.uid == t.owner:
                return s
        return t.seats[0] if t.seats else None

    @staticmethod
    def _need(t: Table) -> int:
        return 1 if t.round > 0 else MIN_PLAYERS

    async def _credit(self, t: Table, uid: int, amount: int):
        if amount:
            await self.eco.add(t.gid, uid, amount)

    async def _sync(self, t: Table, s: Seat):
        """Deja anotado en la base lo que cada persona tiene puesto (por si el bot se reinicia)."""
        if s.stake:
            await self.db.execute("INSERT OR REPLACE INTO web_bj_multi (guild_id, user_id, bet) VALUES (?, ?, ?)", (t.gid, s.uid, s.stake))
        else:
            await self.db.execute("DELETE FROM web_bj_multi WHERE guild_id = ? AND user_id = ?", (t.gid, s.uid))

    async def _admin(self, gid: int, uid: int) -> bool:
        try:
            return bool(await self.svc.admin.is_admin(gid, uid))
        except Exception:
            return False

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
    def _seat_dict(self, t: Table, s: Seat) -> dict:
        v = bj.hand_value(s.cards)
        if t.status == "betting":
            status = "ready" if s.bet else ("done" if s.result else "idle")
        elif not s.playing:
            status = "watch"
        elif s.natural:
            status = "blackjack"
        elif v > 21:
            status = "bust"
        elif s.done:
            status = "stand"
        elif t.cur is s:
            status = "turn"
        else:
            status = "wait"
        names = {x.uid: x.name for x in t.seats}
        return {
            "id": str(s.uid), "name": s.name, "avatar": s.avatar,
            "bet": s.bet, "base_bet": s.base_bet, "doubled": s.doubled, "playing": s.playing,
            "cards": self._cards(s.cards), "value": v if s.cards else None,
            "status": status, "result": s.result,
            "sides": [{"target": str(k), "name": names.get(k, "?"), "amount": a} for k, a in s.sides.items()],
            "side_result": s.side_result,
        }

    def _dict(self, t: Table, uid: int, balance: int, is_admin: bool) -> dict:
        now = time.time()
        betting, playing = t.status == "betting", t.status == "playing"
        mine = next((s for s in t.seats if s.uid == uid), None)
        idx = t.seats.index(mine) if mine else -1
        dealer = self._cards(t.dealer)
        if playing and len(dealer) > 1:
            dealer[1] = None
        if not t.dealer:
            dealer_value = None
        elif playing:
            dealer_value = bj.card_points(t.dealer[0][0])
        else:
            dealer_value = bj.hand_value(t.dealer)
        my_turn = playing and mine is not None and t.cur is mine
        bettors = [s for s in t.seats if s.bet]
        can_deal = betting and len(bettors) >= self._need(t)
        deal_left = None
        if can_deal and len(bettors) == len(t.seats):                       # todos apostaron: se reparte enseguida
            deal_left = max(0.0, t.touched + READY_GRACE - now)
        bet_left = max(0.0, t.bet_deadline - now) if betting and t.bet_deadline else None
        neighbors = []
        if mine and betting:
            for label, off in (("left", -1), ("right", 1)):
                j = idx + off
                if 0 <= j < len(t.seats):
                    o = t.seats[j]
                    neighbors.append({"side": label, "id": str(o.uid), "name": o.name, "bet": o.bet, "mine": mine.sides.get(o.uid, 0)})
        starter = self._starter(t)
        cur = t.cur if playing else None
        return {
            "id": t.id, "v": t.v, "status": t.status, "round": t.round,
            "owner": str(t.owner), "host": str(starter.uid) if starter else None,
            "can_delete": is_admin or uid == t.owner, "admin": is_admin,
            "seats": [self._seat_dict(t, s) for s in t.seats],
            "dealer": dealer, "dealer_value": dealer_value, "dealer_hidden": playing and bool(t.dealer),
            "turn": str(cur.uid) if cur else None,
            "turn_left": round(max(0.0, t.deadline - now), 1) if cur else None,
            "turn_time": TURN_TIME,
            "bet_left": round(bet_left, 1) if bet_left is not None else None,
            "deal_left": round(deal_left, 1) if deal_left is not None else None,
            "can_deal": can_deal, "need": self._need(t),
            "max_seats": MAX_SEATS, "min_players": MIN_PLAYERS,
            "me": {
                "seated": mine is not None, "my_turn": my_turn,
                "can_double": bool(my_turn and len(mine.cards) == 2 and not mine.doubled),
                "bet": mine.bet if mine else 0, "base_bet": mine.base_bet if mine else 0,
                "neighbors": neighbors,
            },
            "balance": balance,
        }

    async def _reply(self, t: Table, uid: int) -> dict:
        balance = await self.eco.balance(t.gid, uid)
        return {"table": self._dict(t, uid, balance, await self._admin(t.gid, uid)), "balance": balance}

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def list(self, gid: int, uid: int) -> dict:
        is_admin = await self._admin(gid, uid)
        out = []
        for t in self.tables.values():
            if t.gid != gid or t.closed:
                continue
            out.append({
                "id": t.id, "status": t.status, "round": t.round, "count": len(t.seats), "max": MAX_SEATS,
                "owner": str(t.owner), "can_delete": is_admin or uid == t.owner,
                "players": [{"id": str(s.uid), "name": s.name, "avatar": s.avatar, "bet": s.bet} for s in t.seats],
            })
        out.sort(key=lambda x: x["id"])
        return {"tables": out, "mine": self.by_user.get((gid, uid)), "max": MAX_SEATS, "admin": is_admin,
                "balance": await self.eco.balance(gid, uid)}

    async def state(self, gid: int, uid: int, tid, since=None) -> dict:
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            await self._tick(t)
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            balance = await self.eco.balance(gid, uid)
            if since is not None and str(since) == str(t.v):
                return {"same": True, "balance": balance}
            return self._dict(t, uid, balance, await self._admin(gid, uid))

    # ------------------------------------------------------------------
    # Mesas: abrir, sentarse, irse, borrar
    # ------------------------------------------------------------------
    async def _sit(self, t: Table, uid: int):
        name, avatar = await self.svc.who(self.svc.guild(t.gid), uid)
        t.seats.append(Seat(uid, name, avatar))
        self.by_user[(t.gid, uid)] = t.id
        self._touch(t)

    async def create(self, gid: int, uid: int) -> dict:
        async with self._gate:
            if (gid, uid) in self.by_user:
                raise ApiError("Ya estás sentado en una mesa. Salí de esa primero.", 409)
            if sum(1 for t in self.tables.values() if t.gid == gid and not t.closed) >= MAX_TABLES:
                raise ApiError("Ya hay muchas mesas abiertas en este servidor. Unite a una.", 409)
            t = Table(next(self._ids), gid, uid)
            await self._sit(t, uid)
            self.tables[t.id] = t
        return await self._reply(t, uid)

    async def join(self, gid: int, uid: int, tid) -> dict:
        t = self._table(gid, tid)
        async with self._gate:
            async with t.lock:
                if t.closed:
                    raise ApiError("Esa mesa ya no existe.", 404)
                if (gid, uid) in self.by_user:
                    raise ApiError("Ya estás sentado en una mesa.", 409)
                if len(t.seats) >= MAX_SEATS:
                    raise ApiError(f"La mesa está llena (máximo {MAX_SEATS}).", 409)
                await self._sit(t, uid)
        return await self._reply(t, uid)

    async def _unseat(self, t: Table, s: Seat):
        """Levanta a alguien de la mesa devolviendo todo lo que tenía puesto (y lo que otros habían puesto por él)."""
        await self._credit(t, s.uid, s.stake)
        s.bet, s.sides = 0, {}
        await self._sync(t, s)
        for o in t.seats:
            if o is not s and s.uid in o.sides:
                await self._credit(t, o.uid, o.sides.pop(s.uid))
                await self._sync(t, o)
        t.seats.remove(s)
        self.by_user.pop((t.gid, s.uid), None)
        self._touch(t)

    async def leave(self, gid: int, uid: int, tid) -> dict:
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            s = self._seat(t, uid)
            if t.status == "playing" and s.playing:
                raise ApiError("No podés irte en medio de una ronda. Jugá tu mano o esperá a que termine.", 409)
            await self._unseat(t, s)
        return {"left": True, "balance": await self.eco.balance(gid, uid)}

    async def delete(self, gid: int, uid: int, tid) -> dict:
        """Borra la mesa (quien la abrió o un admin) y devuelve todas las apuestas, incluso con la ronda empezada."""
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            admin = await self._admin(gid, uid)
            if uid != t.owner and not admin:
                raise ApiError("Solo quien abrió la mesa o un admin puede borrarla.", 403)
            await self._close(t)
            log.info("Web: la mesa de blackjack %d fue borrada por %d%s.", t.id, uid, " (admin)" if admin and uid != t.owner else "")
        return {"deleted": True, "balance": await self.eco.balance(gid, uid)}

    async def _close(self, t: Table):
        for s in list(t.seats):
            await self._credit(t, s.uid, s.stake)
            s.bet, s.sides = 0, {}
            await self._sync(t, s)
            self.by_user.pop((t.gid, s.uid), None)
        t.seats = []
        self._drop(t)

    def _drop(self, t: Table):
        t.closed = True
        self.tables.pop(t.id, None)

    # ------------------------------------------------------------------
    # Apuestas
    # ------------------------------------------------------------------
    async def bet(self, gid: int, uid: int, tid, amount) -> dict:
        """Apuesta (o cambia, o retira con 0) tu mano de la próxima ronda."""
        if amount != 0:
            self._check_bet(amount)
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            await self._tick(t)
            s = self._seat(t, uid)
            if t.status != "betting":
                raise ApiError("Las apuestas están cerradas. Apostá en la próxima ronda.", 409)
            if amount == 0:                                   # retirar: se devuelve todo lo que habías puesto
                await self._credit(t, uid, s.stake)
                s.bet, s.sides = 0, {}
                for o in t.seats:                             # y lo que otros habían puesto por vos
                    if o is not s and uid in o.sides:
                        await self._credit(t, o.uid, o.sides.pop(uid))
                        await self._sync(t, o)
            else:
                delta = amount - s.bet
                if delta > 0 and not await self.eco.add(gid, uid, -delta):
                    raise ApiError("No tenés suficientes monedas para esa apuesta.", 402)
                if delta < 0:
                    await self._credit(t, uid, -delta)
                s.bet = s.base_bet = amount
            await self._sync(t, s)
            self._touch(t)
        return await self._reply(t, uid)

    async def side(self, gid: int, uid: int, tid, target, amount) -> dict:
        """Apuesta por el jugador de tu izquierda o derecha (con 0 la retirás). Cobrás según cómo le vaya a él."""
        if isinstance(target, bool) or not str(target).isdigit():
            raise ApiError("Jugador inválido.")
        target = int(target)
        if amount != 0:
            self._check_bet(amount)
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            await self._tick(t)
            s = self._seat(t, uid)
            if t.status != "betting":
                raise ApiError("Las apuestas están cerradas. Apostá en la próxima ronda.", 409)
            if not s.bet:
                raise ApiError("Primero apostá en tu mano para poder apostar por otros.", 409)
            ts = next((x for x in t.seats if x.uid == target), None)
            if ts is None or abs(t.seats.index(ts) - t.seats.index(s)) != 1:
                raise ApiError("Solo podés apostar por quien se sienta justo a tu izquierda o a tu derecha.", 409)
            if amount and not ts.bet:
                raise ApiError(f"{ts.name} todavía no apostó en su mano.", 409)
            old = s.sides.get(target, 0)
            delta = amount - old
            if delta > 0 and not await self.eco.add(gid, uid, -delta):
                raise ApiError("No tenés suficientes monedas para esa apuesta.", 402)
            if delta < 0:
                await self._credit(t, uid, -delta)
            if amount:
                s.sides[target] = amount
            else:
                s.sides.pop(target, None)
            await self._sync(t, s)
            self._touch(t)
        return await self._reply(t, uid)

    # ------------------------------------------------------------------
    # Ronda
    # ------------------------------------------------------------------
    async def start(self, gid: int, uid: int, tid) -> dict:
        """Repartir antes de que se acabe el tiempo de apuestas."""
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            await self._tick(t)
            s = self._seat(t, uid)
            if t.status != "betting":
                raise ApiError("La ronda ya está en marcha.", 409)
            if self._starter(t) is not s:
                raise ApiError("Solo quien abrió la mesa puede repartir antes de tiempo.", 403)
            if sum(1 for x in t.seats if x.bet) < self._need(t):
                raise ApiError(f"Hacen falta al menos {self._need(t)} jugadores con apuesta para repartir.", 409)
            await self._deal(t)
        return await self._reply(t, uid)

    async def _deal(self, t: Table):
        for s in list(t.seats):                              # quien no apostó se queda mirando; si se repite, se lo levanta
            if s.bet:
                s.missed = 0
            else:
                s.missed += 1
                if s.missed >= MAX_MISSED:
                    await self._unseat(t, s)
        ids = {s.uid for s in t.seats if s.bet}
        for s in t.seats:                                    # apuestas por vecinos que ya no valen: se devuelven
            for target, amt in list(s.sides.items()):
                if target not in ids or not s.bet:
                    s.sides.pop(target)
                    await self._credit(t, s.uid, amt)
            await self._sync(t, s)
        t.round += 1
        t.status = "playing"
        t.bet_deadline = None
        t.shoe = [(r, su) for _ in range(bj.DECKS) for su in bj.SUITS for r in bj.RANKS]
        random.shuffle(t.shoe)
        for s in t.seats:
            s.playing = bool(s.bet)
            s.doubled = False
            s.result = None
            s.side_result = []
            s.cards = [t.shoe.pop(), t.shoe.pop()] if s.playing else []
            s.done = s.natural if s.playing else True        # el blackjack natural no juega: se cobra al final
        t.dealer = [t.shoe.pop(), t.shoe.pop()]
        self._touch(t)
        if bj.is_blackjack(t.dealer):                        # blackjack del dealer: se termina la ronda enseguida
            for s in t.seats:
                s.done = True
        await self._next(t)

    async def act(self, gid: int, uid: int, tid, action) -> dict:
        t = self._table(gid, tid)
        async with t.lock:
            if t.closed:
                raise ApiError("Esa mesa ya no existe.", 404)
            await self._tick(t)                              # por si su turno ya había vencido
            self._seat(t, uid)
            if t.status != "playing":
                raise ApiError("La ronda ya terminó.", 409)
            s = t.cur
            if s is None or s.uid != uid:
                raise ApiError("Todavía no es tu turno.", 409)
            if action == "hit":
                s.cards.append(t.shoe.pop())
                if bj.hand_value(s.cards) >= 21:             # se pasó o llegó a 21: se planta solo
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
                await self._sync(t, s)
                s.cards.append(t.shoe.pop())                 # una sola carta y se planta
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
        for s in t.seats:
            if s.playing and not s.done:
                t.cur = s
                t.deadline = time.time() + TURN_TIME
                return
        t.cur = None
        await self._finish(t)

    async def _tick(self, t: Table):
        """Avanza lo que dependa del reloj: turnos vencidos y tiempo de apuestas."""
        now = time.time()
        if t.status == "playing":
            if t.cur is not None and now > t.deadline + TURN_GRACE:     # su mano se planta sola
                t.cur.done = True
                self._touch(t)
                await self._next(t)
            return
        bettors = [s for s in t.seats if s.bet]
        if len(bettors) >= self._need(t):
            all_bet = len(bettors) == len(t.seats)
            if (all_bet and now - t.touched > READY_GRACE) or (t.bet_deadline and now > t.bet_deadline):
                await self._deal(t)
                return
        if t.bet_deadline and now > t.bet_deadline:                      # se acabó el tiempo y nadie apostó
            for s in list(t.seats):
                s.missed += 1
                if s.missed >= MAX_MISSED:
                    await self._unseat(t, s)
            t.bet_deadline = time.time() + BET_TIME if t.seats else None
            self._touch(t)

    async def _finish(self, t: Table):
        players = [s for s in t.seats if s.playing]
        dealer_nat = bj.is_blackjack(t.dealer)
        live = [s for s in players if not s.natural and bj.hand_value(s.cards) <= 21]
        if live:                                  # el dealer solo juega si queda alguien sin pasarse
            while bj.hand_value(t.dealer) < 17:
                t.dealer.append(t.shoe.pop())
        for s in players:
            if s.natural:
                outcome = "push" if dealer_nat else "blackjack"
            elif dealer_nat:
                outcome = "dealer_blackjack"
            else:
                outcome = bj.final_outcome(SimpleNamespace(player=s.cards, dealer=t.dealer))
            payout = bj.payout_for(outcome, s.bet)
            s.result = {"outcome": outcome, "bet": s.bet, "payout": payout, "net": payout - s.bet, "side_net": 0}
            try:
                await self._credit(t, s.uid, payout)
                await self.svc.record(t.gid, s.uid, "blackjack", s.bet, payout, outcome)
            except Exception:
                log.exception("No pude pagar una mano de blackjack multijugador")
        by_uid = {s.uid: s for s in players}
        for s in players:                         # apuestas por vecinos: cobran según el resultado de ese vecino
            res = []
            for target, amt in s.sides.items():
                ts = by_uid.get(target)
                try:
                    if ts is None:                # no debería pasar: se devuelve
                        await self._credit(t, s.uid, amt)
                        continue
                    outcome = ts.result["outcome"]
                    payout = bj.payout_for(outcome, amt)
                    await self._credit(t, s.uid, payout)
                    res.append({"target": str(target), "name": ts.name, "amount": amt, "outcome": outcome, "net": payout - amt})
                except Exception:
                    log.exception("No pude pagar una apuesta por un vecino")
            s.side_result = res
            s.result["side_net"] = sum(r["net"] for r in res)
        for s in t.seats:                         # todos siguen sentados, con las apuestas en cero
            s.bet, s.sides = 0, {}
            try:
                await self._sync(t, s)
            except Exception:
                log.exception("No pude limpiar el registro de apuestas de una mesa")
        t.status = "betting"
        t.cur = None
        t.shoe = []
        t.bet_deadline = time.time() + BET_TIME
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
                    await self._tick(t)
                    if t.closed:
                        continue
                    idle = now - t.touched
                    if not t.seats and idle > EMPTY_KEEP:
                        self._drop(t)
                    elif t.round == 0 and t.status == "betting" and idle > LOBBY_IDLE:
                        await self._close(t)      # nadie repartió: se devuelve todo y se cierra
                except Exception:
                    log.exception("No pude limpiar una mesa de blackjack")
