"""Lógica del panel web. Usa las mismas reglas, constantes y economía que los comandos del bot."""
import asyncio
import logging
import random
import time
from collections import defaultdict, deque

import discord

from cogs import blackjack as bj
from cogs.economy import DAILY_BASE, DAILY_STREAK_BONUS, DAILY_STREAK_CAP, JOBS, SLOT_MULT, SLOT_PAIR_MULT, SLOT_SYMBOLS, WORK_COOLDOWN, WORK_RANGE
from cogs.economy import MAX_BET as SL_MAX_BET
from cogs.economy import MIN_BET as SL_MIN_BET
from cogs.levels import level_from_xp
from cogs.duels import DuelError
from cogs.tags import TagError
from cogs.roulette import MAX_BET as RL_MAX_BET
from cogs.roulette import MIN_BET as RL_MIN_BET
from utils import roulette as rl
from web.admin import Admin
from web.bjmulti import BJMulti
from web.common import ApiError

log = logging.getLogger("dilus-bot.web")

BJ_IDLE = 180                  # segundos sin actuar: la mano se planta sola
RL_MAX_ZONES = 30              # zonas distintas por tirada
RL_MAX_TOTAL = RL_MAX_BET      # sin tope total (solo alcanza lo que tengas)
PAY_MAX = 1_000_000            # igual que /pay


class Services:
    def __init__(self, bot):
        self.bot = bot
        self.games: dict[tuple[int, int], dict] = {}      # manos de blackjack en juego
        self.expired: dict[tuple[int, int], tuple[float, dict]] = {}   # manos cerradas por inactividad
        self._own_history: dict[int, deque] = {}
        self._locks: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._who: dict[int, tuple[float, tuple[str, str | None]]] = {}
        self.admin = Admin(self)
        self.bjm = BJMulti(self)                           # mesas de blackjack multijugador

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    @property
    def eco(self):
        eco = self.bot.get_cog("Economy")
        if eco is None:
            raise ApiError("La economía del bot no está activa.", 503)
        return eco

    @property
    def db(self):
        return self.bot.db

    def guild(self, gid: int) -> discord.Guild:
        guild = self.bot.get_guild(gid)
        if guild is None:
            raise ApiError("El bot ya no está en ese servidor.", 404)
        return guild

    async def member(self, guild, uid: int):
        member = guild.get_member(uid)
        if member is None:
            try:
                member = await guild.fetch_member(uid)
            except discord.HTTPException:
                member = None
        return member

    async def who(self, guild, uid: int) -> tuple[str, str | None]:
        """(nombre, avatar) de una persona, con caché de 10 minutos."""
        hit = self._who.get(uid)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        obj = guild.get_member(uid) or self.bot.get_user(uid)
        if obj is None:
            try:
                obj = await self.bot.fetch_user(uid)
            except discord.HTTPException:
                obj = None
        info = (obj.display_name, str(obj.display_avatar.with_size(64))) if obj else (f"Usuario {uid}", None)
        self._who[uid] = (time.time(), info)
        if len(self._who) > 2000:
            self._who.clear()
        return info

    def guild_card(self, guild) -> dict:
        return {"id": str(guild.id), "name": guild.name, "icon": str(guild.icon.with_size(64)) if guild.icon else None}

    async def record(self, gid: int, uid: int, game: str, wagered: int, returned: int, detail: str = ""):
        best = max(0, returned - wagered)
        await self.db.execute(
            "INSERT INTO casino_log (guild_id, user_id, game, bet, returned, detail, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (gid, uid, game, wagered, returned, detail[:40], time.time()),
        )
        await self.db.execute(     # solo se guardan las últimas 200 jugadas por persona
            "DELETE FROM casino_log WHERE guild_id = ? AND user_id = ? AND id NOT IN "
            "(SELECT id FROM casino_log WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 200)",
            (gid, uid, gid, uid),
        )
        await self.db.execute(
            "INSERT INTO casino_stats (guild_id, user_id, game, played, wagered, returned, best) VALUES (?, ?, ?, 1, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, game) DO UPDATE SET played = played + 1, wagered = wagered + excluded.wagered, "
            "returned = returned + excluded.returned, best = MAX(best, excluded.best)",
            (gid, uid, game, wagered, returned, best),
        )

    # ------------------------------------------------------------------
    # Perfil
    # ------------------------------------------------------------------
    async def profile(self, gid: int, uid: int) -> dict:
        row = await self.eco.get_row(gid, uid)
        now = time.time()
        bal = row["balance"]
        rank = (await self.db.fetchone("SELECT COUNT(*) + 1 AS p FROM economy WHERE guild_id = ? AND balance > ?", (gid, bal)))["p"]

        lv = await self.db.fetchone("SELECT xp, messages, voice_seconds FROM levels WHERE guild_id = ? AND user_id = ?", (gid, uid))
        xp = lv["xp"] if lv else 0
        level, into, need = level_from_xp(xp)
        xp_rank = None
        if lv:
            xp_rank = (await self.db.fetchone("SELECT COUNT(*) + 1 AS p FROM levels WHERE guild_id = ? AND xp > ?", (gid, xp)))["p"]

        last_daily = row["last_daily"]
        alive = 0 < last_daily and now - last_daily < 172800
        streak = row["streak"] if alive else 0
        next_streak = streak + 1 if alive else 1

        casino = {}
        for r in await self.db.fetchall("SELECT game, played, wagered, returned, best FROM casino_stats WHERE guild_id = ? AND user_id = ?", (gid, uid)):
            casino[r["game"]] = {k: r[k] for k in ("played", "wagered", "returned", "best")}

        return {
            "now": now,
            "is_admin": await self.admin.is_admin(gid, uid),
            "balance": bal,
            "eco_rank": rank,
            "level": {
                "level": level, "xp_in": into, "xp_need": need, "xp_total": xp, "rank": xp_rank,
                "messages": lv["messages"] if lv else 0, "voice_seconds": lv["voice_seconds"] if lv else 0,
            },
            "daily": {
                "ready_at": last_daily + 86400 if last_daily else 0, "streak": streak,
                "next_reward": DAILY_BASE + min(next_streak - 1, DAILY_STREAK_CAP) * DAILY_STREAK_BONUS,
                "base": DAILY_BASE, "bonus": DAILY_STREAK_BONUS, "cap": DAILY_STREAK_CAP,
            },
            "work": {"ready_at": row["last_work"] + WORK_COOLDOWN if row["last_work"] else 0, "min": WORK_RANGE[0], "max": WORK_RANGE[1], "cooldown": WORK_COOLDOWN},
            "casino": casino,
            "limits": {"bj_min": bj.MIN_BET, "bj_max": bj.MAX_BET, "rl_min": RL_MIN_BET, "rl_max": RL_MAX_BET, "sl_min": SL_MIN_BET, "sl_max": SL_MAX_BET, "cf_min": SL_MIN_BET, "cf_max": SL_MAX_BET, "pay_max": PAY_MAX},
            "slots": {"symbols": SLOT_SYMBOLS, "mult": SLOT_MULT, "pair": SLOT_PAIR_MULT},
        }

    # ------------------------------------------------------------------
    # Reclamos (mismas reglas que /daily y /trabajar)
    # ------------------------------------------------------------------
    async def claim_daily(self, gid: int, uid: int) -> dict:
        async with self._locks[(gid, uid)]:
            row = await self.eco.get_row(gid, uid)
            now, last = time.time(), row["last_daily"]
            if now - last < 86400:
                raise ApiError("Ya reclamaste tu diaria.", 409, ready_at=last + 86400)
            streak = row["streak"] + 1 if 0 < last and now - last < 172800 else 1
            reward = DAILY_BASE + min(streak - 1, DAILY_STREAK_CAP) * DAILY_STREAK_BONUS
            cur = await self.db.execute(
                "UPDATE economy SET balance = balance + ?, last_daily = ?, streak = ? WHERE guild_id = ? AND user_id = ? AND last_daily = ?",
                (reward, now, streak, gid, uid, last),
            )
            if cur.rowcount == 0:
                raise ApiError("Ya reclamaste tu diaria.", 409)
            return {"reward": reward, "streak": streak, "ready_at": now + 86400, "balance": await self.eco.balance(gid, uid)}

    async def claim_work(self, gid: int, uid: int) -> dict:
        async with self._locks[(gid, uid)]:
            row = await self.eco.get_row(gid, uid)
            now, last = time.time(), row["last_work"]
            if now - last < WORK_COOLDOWN:
                raise ApiError("Estás cansado, volvé más tarde.", 409, ready_at=last + WORK_COOLDOWN)
            reward = random.randint(*WORK_RANGE)
            cur = await self.db.execute(
                "UPDATE economy SET balance = balance + ?, last_work = ? WHERE guild_id = ? AND user_id = ? AND last_work = ?",
                (reward, now, gid, uid, last),
            )
            if cur.rowcount == 0:
                raise ApiError("Ya estás trabajando.", 409)
            return {"reward": reward, "job": random.choice(JOBS), "ready_at": now + WORK_COOLDOWN, "balance": await self.eco.balance(gid, uid)}

    # ------------------------------------------------------------------
    # Tienda de roles
    # ------------------------------------------------------------------
    async def shop(self, gid: int, uid: int) -> dict:
        guild = self.guild(gid)
        member = await self.member(guild, uid)
        rows = await self.db.fetchall("SELECT role_id, price FROM shop WHERE guild_id = ? ORDER BY price", (gid,))
        items = []
        for r in rows:
            role = guild.get_role(r["role_id"])
            if role is None:
                continue
            items.append({
                "id": str(role.id), "name": role.name, "price": r["price"],
                "color": f"#{role.color.value:06x}" if role.color.value else None,
                "owned": bool(member and role in member.roles),
                "available": role < guild.me.top_role,
            })
        return {"items": items, "balance": await self.eco.balance(gid, uid)}

    async def buy(self, gid: int, uid: int, role_id) -> dict:
        guild = self.guild(gid)
        member = await self.member(guild, uid)
        if member is None:
            raise ApiError("No te encuentro en el servidor.", 404)
        try:
            rid = int(role_id)
        except (TypeError, ValueError):
            raise ApiError("Rol inválido.")
        item = await self.db.fetchone("SELECT price FROM shop WHERE guild_id = ? AND role_id = ?", (gid, rid))
        role = guild.get_role(rid)
        if not item or role is None:
            raise ApiError("Ese rol no está en la tienda.", 404)
        if role in member.roles:
            raise ApiError("Ya tenés ese rol.", 409)
        if role >= guild.me.top_role:
            raise ApiError("No puedo darte ese rol (está por encima del mío).", 409)
        async with self._locks[(gid, uid)]:
            if not await self.eco.add(gid, uid, -item["price"]):
                raise ApiError("No tenés suficientes monedas.", 402)
            try:
                await member.add_roles(role, reason="Compra en el panel web - Dilu's Bot")
            except discord.HTTPException:
                await self.eco.add(gid, uid, item["price"])  # devolución
                raise ApiError("No pude darte el rol. No se cobró nada.", 500)
        return {"role": role.name, "price": item["price"], "balance": await self.eco.balance(gid, uid)}

    # ------------------------------------------------------------------
    # Tags de colores (misma lógica que /tags)
    # ------------------------------------------------------------------
    @property
    def tagcog(self):
        cog = self.bot.get_cog("Tags")
        if cog is None:
            raise ApiError("Los tags no están activos.", 503)
        return cog

    async def tags(self, gid: int, uid: int) -> dict:
        guild = self.guild(gid)
        member = await self.member(guild, uid)
        return {"items": await self.tagcog.catalog(guild, member), "balance": await self.eco.balance(gid, uid)}

    async def _tag_action(self, gid: int, uid: int, fn):
        guild = self.guild(gid)
        member = await self.member(guild, uid)
        if member is None:
            raise ApiError("No te encuentro en el servidor.", 404)
        try:
            tag = await fn(guild, member)
        except TagError as e:
            raise ApiError(e.message, e.status)
        return {"tag": tag.name if tag else None, "price": tag.price if tag else 0, "balance": await self.eco.balance(gid, uid)}

    async def tag_buy(self, gid: int, uid: int, key) -> dict:
        return await self._tag_action(gid, uid, lambda g, m: self.tagcog.buy(g, m, key))

    async def tag_equip(self, gid: int, uid: int, key) -> dict:
        """key = None -> sacarse el tag."""
        if key is None:
            async def off(g, m):
                await self.tagcog.unequip(m)
                return None
            return await self._tag_action(gid, uid, off)
        return await self._tag_action(gid, uid, lambda g, m: self.tagcog.equip(g, m, key))

    # ------------------------------------------------------------------
    # Rankings
    # ------------------------------------------------------------------
    async def leaderboard(self, gid: int, uid: int, kind: str) -> dict:
        guild = self.guild(gid)
        if kind == "xp":
            rows = await self.db.fetchall("SELECT user_id, xp, messages FROM levels WHERE guild_id = ? AND xp > 0 ORDER BY xp DESC LIMIT 10", (gid,))
            mine = await self.db.fetchone("SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?", (gid, uid))
            my_value = mine["xp"] if mine else 0
            my_pos = (await self.db.fetchone("SELECT COUNT(*) + 1 AS p FROM levels WHERE guild_id = ? AND xp > ?", (gid, my_value)))["p"] if mine else None
        else:
            kind = "eco"
            rows = await self.db.fetchall("SELECT user_id, balance FROM economy WHERE guild_id = ? AND balance > 0 ORDER BY balance DESC LIMIT 10", (gid,))
            my_value = await self.eco.balance(gid, uid)
            my_pos = (await self.db.fetchone("SELECT COUNT(*) + 1 AS p FROM economy WHERE guild_id = ? AND balance > ?", (gid, my_value)))["p"]

        entries = []
        for r in rows:
            name, avatar = await self.who(guild, r["user_id"])
            if kind == "xp":
                level = level_from_xp(r["xp"])[0]
                entries.append({"id": str(r["user_id"]), "name": name, "avatar": avatar, "value": r["xp"], "level": level, "sub": f"{r['messages']} mensajes"})
            else:
                entries.append({"id": str(r["user_id"]), "name": name, "avatar": avatar, "value": r["balance"]})
        return {"type": kind, "entries": entries, "me": {"id": str(uid), "position": my_pos, "value": my_value}}

    # ------------------------------------------------------------------
    # Blackjack (mismas reglas que /blackjack)
    # ------------------------------------------------------------------
    async def recover(self):
        """Si el bot se reinició con manos abiertas, devuelve las apuestas."""
        rows = await self.db.fetchall("SELECT guild_id, user_id, bet FROM web_blackjack")
        for r in rows:
            await self.db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", (r["guild_id"], r["user_id"]))
            await self.db.execute(
                "UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (r["bet"], r["guild_id"], r["user_id"])
            )
        if rows:
            await self.db.execute("DELETE FROM web_blackjack")
            log.info("Web: devolví las apuestas de %d mano(s) de blackjack que quedaron abiertas.", len(rows))
        await self.bjm.recover()

    def _bj_dict(self, g: bj.Game, balance: int) -> dict:
        active = g.outcome is None
        hole = g.hide_hole and active
        dealer = [list(c) for c in g.dealer]
        if hole:
            dealer[1] = None
        return {
            "active": active,
            "bet": g.bet, "base_bet": g.base_bet, "doubled": g.doubled,
            "player": [list(c) for c in g.player], "player_value": bj.hand_value(g.player),
            "dealer": dealer, "dealer_value": bj.card_points(g.dealer[0][0]) if hole else bj.hand_value(g.dealer),
            "dealer_hidden": hole,
            "outcome": g.outcome, "payout": g.payout, "net": (g.payout - g.bet) if g.outcome else None,
            "can_double": active and len(g.player) == 2 and not g.doubled,
            "balance": balance,
        }

    async def bj_state(self, gid: int, uid: int) -> dict:
        key = (gid, uid)
        balance = await self.eco.balance(gid, uid)
        if key in self.games:
            return {"game": self._bj_dict(self.games[key]["game"], balance), "balance": balance}
        done = self.expired.pop(key, None)
        return {"game": None, "expired": done[1] if done else None, "balance": balance}

    async def _bj_settle(self, key: tuple[int, int]) -> bj.Game:
        entry = self.games.pop(key)
        g: bj.Game = entry["game"]
        g.payout = bj.payout_for(g.outcome or "lose", g.bet)
        if g.payout:
            await self.eco.add(g.guild_id, g.user_id, g.payout)
        await self.db.execute("DELETE FROM web_blackjack WHERE guild_id = ? AND user_id = ?", (g.guild_id, g.user_id))
        await self.record(g.guild_id, g.user_id, "blackjack", g.bet, g.payout, g.outcome or "")
        return g

    async def _bj_finish(self, key: tuple[int, int]) -> bj.Game:
        g: bj.Game = self.games[key]["game"]
        g.hide_hole = False
        if bj.hand_value(g.player) <= 21:                 # el dealer solo juega si el jugador no se pasó
            while bj.hand_value(g.dealer) < 17:
                g.dealer.append(g.shoe.pop())
        g.outcome = bj.final_outcome(g)
        return await self._bj_settle(key)

    async def _bj_reply(self, g: bj.Game, **extra) -> dict:
        balance = await self.eco.balance(g.guild_id, g.user_id)
        return {"game": self._bj_dict(g, balance), "balance": balance, **extra}

    async def bj_deal(self, gid: int, uid: int, bet) -> dict:
        if not isinstance(bet, int) or isinstance(bet, bool) or not bj.MIN_BET <= bet <= bj.MAX_BET:
            raise ApiError(f"La apuesta mínima es {bj.MIN_BET} monedas.")
        key = (gid, uid)
        async with self._locks[key]:
            if key in self.games:
                raise ApiError("Ya tenés una mano en juego. Terminala primero.", 409)
            if not await self.eco.add(gid, uid, -bet):
                raise ApiError("No tenés suficientes monedas para esa apuesta.", 402)
            g = bj.Game(gid, uid, bet)
            await self.db.execute("INSERT OR REPLACE INTO web_blackjack (guild_id, user_id, bet) VALUES (?, ?, ?)", (gid, uid, bet))
            self.games[key] = {"game": g, "last": time.time()}
            outcome = bj.initial_outcome(g)
            if outcome:                                   # blackjack natural (tuyo o del dealer)
                g.hide_hole = False
                g.outcome = outcome
                await self._bj_settle(key)
            return await self._bj_reply(g)

    async def bj_action(self, gid: int, uid: int, action: str) -> dict:
        key = (gid, uid)
        async with self._locks[key]:
            entry = self.games.get(key)
            if entry is None:
                raise ApiError("No tenés ninguna mano en juego.", 404)
            g: bj.Game = entry["game"]
            entry["last"] = time.time()
            if action == "hit":
                g.player.append(g.shoe.pop())
                if bj.hand_value(g.player) >= 21:         # se pasó o llegó a 21: se planta solo
                    await self._bj_finish(key)
            elif action == "stand":
                await self._bj_finish(key)
            elif action == "double":
                if g.doubled or len(g.player) != 2:
                    raise ApiError("Solo podés doblar con tus dos primeras cartas.", 409)
                if not await self.eco.add(gid, uid, -g.base_bet):
                    raise ApiError("No te alcanzan las monedas para doblar.", 402)
                g.bet += g.base_bet
                g.doubled = True
                await self.db.execute("UPDATE web_blackjack SET bet = ? WHERE guild_id = ? AND user_id = ?", (g.bet, gid, uid))
                g.player.append(g.shoe.pop())             # una sola carta y se planta
                await self._bj_finish(key)
            else:
                raise ApiError("Acción inválida.")
            return await self._bj_reply(g)

    async def sweep(self):
        """Cierra las manos abandonadas (se plantan solas, igual que en Discord)."""
        now = time.time()
        for key, entry in list(self.games.items()):
            if now - entry["last"] <= BJ_IDLE:
                continue
            async with self._locks[key]:
                if key not in self.games or time.time() - self.games[key]["last"] <= BJ_IDLE:
                    continue
                try:
                    g = await self._bj_finish(key)
                    self.expired[key] = (time.time(), self._bj_dict(g, await self.eco.balance(*key)))
                except Exception:
                    log.exception("No pude cerrar una mano de blackjack abandonada")
        for key, (stamp, _) in list(self.expired.items()):    # avisos viejos que nadie vio
            if now - stamp > 3600:
                self.expired.pop(key, None)
        await self.bjm.sweep()                                # turnos vencidos y mesas abandonadas

    # ------------------------------------------------------------------
    # Ruleta (mismas reglas y pagos que /ruleta)
    # ------------------------------------------------------------------
    @staticmethod
    def _valid_zone(key) -> bool:
        if not isinstance(key, str):
            return False
        if key in rl.BET_TYPES:
            return True
        return key.startswith("n") and key[1:].isdigit() and key == f"n{int(key[1:])}" and 0 <= int(key[1:]) <= 36

    def _rl_history(self, gid: int) -> deque:
        cog = self.bot.get_cog("Roulette")
        store = cog.history if cog is not None else self._own_history
        return store.setdefault(gid, deque(maxlen=20))

    async def roulette_history(self, gid: int) -> dict:
        return {"history": list(self._rl_history(gid))[-14:]}

    async def roulette_spin(self, gid: int, uid: int, bets) -> dict:
        if not isinstance(bets, list) or not bets:
            raise ApiError("Poné al menos una ficha en el tablero.")
        merged: dict[str, int] = {}
        for b in bets:
            if not isinstance(b, dict) or not self._valid_zone(b.get("key")):
                raise ApiError("Apuesta inválida.")
            amount = b.get("amount")
            if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
                raise ApiError("Monto inválido.")
            merged[b["key"]] = merged.get(b["key"], 0) + amount
        if len(merged) > RL_MAX_ZONES:
            raise ApiError(f"Como máximo {RL_MAX_ZONES} zonas distintas por tirada.")
        for key, amount in merged.items():
            if not RL_MIN_BET <= amount <= RL_MAX_BET:
                raise ApiError(f"Cada apuesta tiene que ser de al menos {RL_MIN_BET} monedas (revisá {rl.bet_info(key).label}).")
        total = sum(merged.values())
        if total > RL_MAX_TOTAL:
            raise ApiError("El total de la tirada es demasiado grande.")

        async with self._locks[(gid, uid)]:
            if not await self.eco.add(gid, uid, -total):
                raise ApiError("No tenés suficientes monedas para esa tirada.", 402)
            number = rl.spin()
            results, returned = [], 0
            for key, amount in merged.items():
                back = rl.payout(key, amount, number)
                returned += back
                info = rl.bet_info(key)
                results.append({"key": key, "label": info.label, "amount": amount, "payout": back, "won": back > 0})
            if returned:
                await self.eco.add(gid, uid, returned)
            await self.record(gid, uid, "roulette", total, returned, str(number))
            hist = self._rl_history(gid)
            hist.append(number)
            return {
                "number": number, "color": rl.color_of(number), "tags": rl.number_tags(number),
                "results": results, "total_bet": total, "total_return": returned, "net": returned - total,
                "balance": await self.eco.balance(gid, uid), "history": list(hist)[-14:],
            }

    # ------------------------------------------------------------------
    # Tragamonedas (mismas reglas y pagos que /slots)
    # ------------------------------------------------------------------
    async def slots_spin(self, gid: int, uid: int, bet) -> dict:
        if not isinstance(bet, int) or isinstance(bet, bool) or not SL_MIN_BET <= bet <= SL_MAX_BET:
            raise ApiError(f"La apuesta mínima es {SL_MIN_BET} monedas.")
        async with self._locks[(gid, uid)]:
            if not await self.eco.add(gid, uid, -bet):
                raise ApiError("No tenés suficientes monedas para esa apuesta.", 402)
            rng = random.SystemRandom()
            reels = [rng.choice(SLOT_SYMBOLS) for _ in range(3)]
            if len(set(reels)) == 1:
                payout, kind, mult = bet * SLOT_MULT[reels[0]], "jackpot", SLOT_MULT[reels[0]]
            elif len(set(reels)) == 2:
                payout, kind, mult = int(bet * SLOT_PAIR_MULT), "pair", SLOT_PAIR_MULT
            else:
                payout, kind, mult = 0, "none", 0
            if payout:
                await self.eco.add(gid, uid, payout)
            await self.record(gid, uid, "slots", bet, payout, " ".join(reels))
            return {"reels": reels, "kind": kind, "mult": mult, "payout": payout, "net": payout - bet, "balance": await self.eco.balance(gid, uid)}

    # ------------------------------------------------------------------
    # Cara o cruz (mismas reglas que /apostar: si acertás, duplicás lo apostado)
    # ------------------------------------------------------------------
    async def coinflip(self, gid: int, uid: int, bet, side) -> dict:
        if not isinstance(bet, int) or isinstance(bet, bool) or not SL_MIN_BET <= bet <= SL_MAX_BET:
            raise ApiError(f"La apuesta mínima es {SL_MIN_BET} monedas.")
        if side not in ("cara", "cruz"):
            raise ApiError("Elegí cara o cruz.")
        async with self._locks[(gid, uid)]:
            if not await self.eco.add(gid, uid, -bet):
                raise ApiError("No tenés suficientes monedas para esa apuesta.", 402)
            result = random.SystemRandom().choice(["cara", "cruz"])
            won = result == side
            payout = bet * 2 if won else 0
            if payout:
                await self.eco.add(gid, uid, payout)
            await self.record(gid, uid, "coinflip", bet, payout, result)
            return {"result": result, "side": side, "won": won, "payout": payout, "net": payout - bet, "balance": await self.eco.balance(gid, uid)}

    # ------------------------------------------------------------------
    # Duelos de cara o cruz contra otra persona (misma lógica que /caracruz duelo)
    # ------------------------------------------------------------------
    @property
    def duelcog(self):
        cog = self.bot.get_cog("Duels")
        if cog is None:
            raise ApiError("Los duelos no están activos.", 503)
        return cog

    async def duel_list(self, gid: int, uid: int) -> dict:
        self.guild(gid)
        data = await self.duelcog.listing(gid, uid)
        data["balance"] = await self.eco.balance(gid, uid)
        return data

    async def duel_create(self, gid: int, uid: int, target, bet, side) -> dict:
        guild = self.guild(gid)
        me = await self.member(guild, uid)
        if me is None:
            raise ApiError("No te encuentro en el servidor.", 404)
        if not isinstance(target, str) or not target.isdigit():
            raise ApiError("Elegí a una persona.")
        opp = await self.member(guild, int(target))
        if opp is None:
            raise ApiError("No encuentro a esa persona en el servidor.", 404)
        try:
            row = await self.duelcog.create(guild, me, opp, bet, side, source="web")
        except DuelError as e:
            raise ApiError(e.message, e.status)
        dm = await self.duelcog.announce(row, opponent=opp)      # aviso por mensaje privado (si lo tiene abierto)
        return {"id": row["id"], "opponent": opp.display_name, "dm": dm, "balance": await self.eco.balance(gid, uid)}

    async def _duel_action(self, gid: int, uid: int, duel_id, name: str) -> dict:
        self.guild(gid)
        if not isinstance(duel_id, int) or isinstance(duel_id, bool):
            raise ApiError("Duelo inválido.")
        row = await self.db.fetchone("SELECT guild_id FROM coin_duels WHERE id = ?", (duel_id,))
        if row is None or row["guild_id"] != gid:
            raise ApiError("Ese duelo no existe.", 404)
        try:
            res = await getattr(self.duelcog, name)(duel_id, uid)
        except DuelError as e:
            raise ApiError(e.message, e.status)
        out = {"id": duel_id, "balance": await self.eco.balance(gid, uid)}
        if res is not None:
            out.update(result=res["result"], winner_id=str(res["winner_id"]), won=res["winner_id"] == uid, bet=res["bet"])
        return out

    async def duel_accept(self, gid, uid, duel_id): return await self._duel_action(gid, uid, duel_id, "accept")
    async def duel_decline(self, gid, uid, duel_id): return await self._duel_action(gid, uid, duel_id, "decline")
    async def duel_cancel(self, gid, uid, duel_id): return await self._duel_action(gid, uid, duel_id, "cancel")

    # ------------------------------------------------------------------
    # Enviar monedas (mismas reglas que /pay)
    # ------------------------------------------------------------------
    async def members(self, gid: int, uid: int, query) -> dict:
        q = str(query or "").strip().lower()[:32]
        if not q:
            return {"members": []}
        guild = self.guild(gid)
        found = []
        for m in guild.members:
            if m.bot or m.id == uid:
                continue
            name = m.display_name.lower()
            if q in name or q in m.name.lower():
                found.append((0 if name.startswith(q) else 1, name, m))
        found.sort(key=lambda t: (t[0], t[1]))
        return {"members": [{"id": str(m.id), "name": m.display_name, "avatar": str(m.display_avatar.with_size(64))} for _, _, m in found[:8]]}

    async def pay(self, gid: int, uid: int, target, amount) -> dict:
        if not isinstance(amount, int) or isinstance(amount, bool) or not 1 <= amount <= PAY_MAX:
            raise ApiError(f"El monto tiene que estar entre 1 y {PAY_MAX}.")
        if not isinstance(target, str) or not target.isdigit() or int(target) == uid:
            raise ApiError("Elegí a otra persona (no bots ni vos mismo).")
        member = self.guild(gid).get_member(int(target))
        if member is None or member.bot:
            raise ApiError("No encuentro a esa persona en el servidor.", 404)
        async with self._locks[(gid, uid)]:
            if not await self.eco.add(gid, uid, -amount):
                raise ApiError("No tenés suficientes monedas.", 402)
            await self.eco.add(gid, member.id, amount)
        return {"to": member.display_name, "amount": amount, "balance": await self.eco.balance(gid, uid)}

    # ------------------------------------------------------------------
    # Historial y logros
    # ------------------------------------------------------------------
    async def activity(self, gid: int, uid: int) -> dict:
        rows = await self.db.fetchall(
            "SELECT game, bet, returned, detail, ts FROM casino_log WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 40", (gid, uid)
        )
        ordered = list(reversed(rows))
        total, series = 0, []
        for r in ordered:
            total += r["returned"] - r["bet"]
            series.append(total)
        items = [
            {"game": r["game"], "bet": r["bet"], "returned": r["returned"], "net": r["returned"] - r["bet"], "detail": r["detail"], "ts": r["ts"]}
            for r in rows[:12]
        ]
        return {"items": items, "series": series, "total_net": total, "count": len(rows)}

    async def achievements(self, gid: int, uid: int) -> dict:
        p = await self.profile(gid, uid)
        guild = self.guild(gid)
        member = await self.member(guild, uid)
        owned = 0
        for r in await self.db.fetchall("SELECT role_id FROM shop WHERE guild_id = ?", (gid,)):
            role = guild.get_role(r["role_id"])
            if member and role and role in member.roles:
                owned += 1
        cs, lv = p["casino"], p["level"]
        played = lambda game: cs.get(game, {}).get("played", 0)
        best = max([c["best"] for c in cs.values()] or [0])
        hours = lv["voice_seconds"] / 3600
        defs = [
            ("eco1", "🪙", "Ahorrista", "Juntá 10.000 monedas", p["balance"], 10_000, "bronze"),
            ("eco2", "💰", "Adinerado", "Juntá 50.000 monedas", p["balance"], 50_000, "silver"),
            ("eco3", "🏦", "Magnate", "Juntá 250.000 monedas", p["balance"], 250_000, "gold"),
            ("lvl1", "⭐", "Novato", "Llegá al nivel 5", lv["level"], 5, "bronze"),
            ("lvl2", "🌟", "Veterano", "Llegá al nivel 10", lv["level"], 10, "silver"),
            ("lvl3", "👑", "Leyenda", "Llegá al nivel 25", lv["level"], 25, "gold"),
            ("str1", "🔥", "Constante", "Racha diaria de 3 días", p["daily"]["streak"], 3, "bronze"),
            ("str2", "🔥", "Disciplinado", "Racha diaria de 7 días", p["daily"]["streak"], 7, "silver"),
            ("str3", "☄️", "Imparable", "Racha diaria de 14 días", p["daily"]["streak"], 14, "gold"),
            ("chat1", "💬", "Charlatán", "Enviá 100 mensajes", lv["messages"], 100, "bronze"),
            ("chat2", "📣", "Alma del chat", "Enviá 1.000 mensajes", lv["messages"], 1000, "silver"),
            ("voz1", "🎧", "Oyente", "Pasá 10 horas en voz", hours, 10, "bronze"),
            ("voz2", "🎙️", "Locutor", "Pasá 50 horas en voz", hours, 50, "silver"),
            ("rl1", "🎡", "Apostador", "Jugá 10 veces a la ruleta", played("roulette"), 10, "bronze"),
            ("rl2", "🎡", "Habitué", "Jugá 100 veces a la ruleta", played("roulette"), 100, "silver"),
            ("bj1", "🃏", "Cartero", "Jugá 10 manos de blackjack", played("blackjack"), 10, "bronze"),
            ("bj2", "♠️", "Tahúr", "Jugá 100 manos de blackjack", played("blackjack"), 100, "silver"),
            ("sl1", "🎰", "Tragamonedas", "Jugá 25 veces a los slots", played("slots"), 25, "bronze"),
            ("win1", "🍀", "Golpe de suerte", "Ganá 1.000 monedas de una sola vez", best, 1000, "silver"),
            ("win2", "💎", "Jackpot", "Ganá 10.000 monedas de una sola vez", best, 10_000, "gold"),
            ("shop1", "🛍️", "Coleccionista", "Comprá un rol de la tienda", owned, 1, "bronze"),
        ]
        items = [
            {"id": i, "icon": ic, "name": n, "desc": d, "value": round(v, 1), "goal": g, "tier": t, "unlocked": v >= g}
            for i, ic, n, d, v, g, t in defs
        ]
        return {"items": items, "unlocked": sum(1 for x in items if x["unlocked"]), "total": len(items)}
