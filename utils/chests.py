"""Servicio central de cofres. Lo usan los comandos de Discord Y el panel web: la lógica no está duplicada.

Garantías (las dan los triggers de utils/db.py, no el código de acá):
- Abrir un cofre es UNA sola sentencia SQL: valida, consume (racha o inventario), registra el historial y acredita las monedas.
  Si algo falla no se aplica nada. Reintentos con el mismo request_id devuelven la misma apertura (nunca pagan dos veces).
- Comprar un cofre es UNA sola sentencia: cobra y suma al inventario, o no hace nada.
- La recompensa se sortea acá, en el servidor, ANTES de que exista ninguna animación.
"""
import asyncio
import random
import re
import sqlite3
import time
import uuid
from collections import defaultdict

from utils import chest_config as cc

_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ChestError(Exception):
    """Error con mensaje listo para mostrar. `code` sirve para que Discord/web decidan qué hacer."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


class ChestService:
    def __init__(self, bot, clock=time.time, rng: random.Random | None = None):
        self.bot = bot
        self.clock = clock
        self.rng = rng
        self._locks: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    @property
    def db(self):
        return self.bot.db

    async def _balance(self, gid: int, uid: int) -> int:
        eco = self.bot.get_cog("Economy")
        if eco is None:
            raise ChestError("unavailable", "La economía del bot no está activa.")
        return await eco.balance(gid, uid)

    @staticmethod
    def _key(gid: int, uid: int, request_id: str | None) -> str:
        """Identificador único de la solicitud. Incluye servidor y persona: nadie puede reutilizar el de otra persona."""
        if request_id is None:
            request_id = uuid.uuid4().hex
        if not isinstance(request_id, str) or not _REQUEST_ID.match(request_id):
            raise ChestError("bad_request", "Solicitud inválida.")
        return f"{gid}:{uid}:{request_id}"

    # ------------------------------------------------------------------
    # Configuración (precios y escala editables por los admins)
    # ------------------------------------------------------------------
    async def settings(self, gid: int) -> dict:
        rows = await self.db.fetchall("SELECT key, value FROM chest_settings WHERE guild_id = ?", (gid,))
        raw = {r["key"]: r["value"] for r in rows}
        prices = {}
        for rarity in cc.RARITIES:
            try:
                prices[rarity] = int(raw.get(f"price_{rarity}", cc.DEFAULT_PRICES[rarity]))
            except ValueError:
                prices[rarity] = cc.DEFAULT_PRICES[rarity]
        try:
            scale = min(cc.SCALE_MAX, max(cc.SCALE_MIN, float(raw.get("reward_scale", 1.0))))
        except ValueError:
            scale = 1.0
        return {"prices": prices, "scale": scale}

    async def _put_setting(self, gid: int, key: str, value):
        await self.db.execute(
            "INSERT INTO chest_settings (guild_id, key, value) VALUES (?, ?, ?) ON CONFLICT (guild_id, key) DO UPDATE SET value = excluded.value",
            (gid, key, str(value)),
        )

    async def set_price(self, gid: int, rarity: str, price: int):
        if rarity not in cc.RARITIES or not cc.PRICE_MIN <= price <= cc.PRICE_MAX:
            raise ChestError("invalid", f"El precio tiene que estar entre {cc.PRICE_MIN} y {cc.PRICE_MAX}.")
        await self._put_setting(gid, f"price_{rarity}", price)

    async def set_scale(self, gid: int, scale: float):
        if not cc.SCALE_MIN <= scale <= cc.SCALE_MAX:
            raise ChestError("invalid", f"La escala tiene que estar entre {cc.SCALE_MIN} y {cc.SCALE_MAX}.")
        await self._put_setting(gid, "reward_scale", round(scale, 3))

    async def public_config(self, gid: int) -> dict:
        """Todo lo que la interfaz necesita para mostrar precios, rangos y probabilidades (transparencia total)."""
        s = await self.settings(gid)
        out = {}
        for rarity in cc.RARITIES:
            segs = cc.segments(rarity, s["scale"])
            ev = cc.expected_value(rarity, s["scale"])
            out[rarity] = {
                "name": cc.RARITY_NAME[rarity], "color": cc.RARITY_HEX[rarity], "price": s["prices"][rarity],
                "min": segs[0]["lo"], "max": segs[-1]["hi"], "ev": round(ev, 1), "return_pct": round(ev / s["prices"][rarity] * 100, 1),
                "segments": segs,
            }
        return {"rarities": out, "scale": s["scale"], "progression": cc.STREAK_PROGRESSION, "max_buy": cc.MAX_BUY_QTY}

    # ------------------------------------------------------------------
    # Lectura de estado
    # ------------------------------------------------------------------
    async def inventory(self, gid: int, uid: int) -> dict:
        rows = await self.db.fetchall("SELECT rarity, qty FROM chest_inventory WHERE guild_id = ? AND user_id = ?", (gid, uid))
        inv = {r: 0 for r in cc.RARITIES}
        for row in rows:
            if row["rarity"] in inv:
                inv[row["rarity"]] = row["qty"]
        return inv

    async def daily_info(self, gid: int, uid: int) -> dict:
        row = await self.db.fetchone("SELECT streak, best_streak, last_claim, claims FROM chest_state WHERE guild_id = ? AND user_id = ?", (gid, uid))
        last, streak, best, claims = (row["last_claim"], row["streak"], row["best_streak"], row["claims"]) if row else (0.0, 0, 0, 0)
        info = cc.streak_status(last, streak, self.clock())
        return {
            "streak": info["streak"], "best_streak": best, "claims": claims, "available": info["available"], "ready_at": info["ready_at"],
            "expires_at": info["expires_at"], "streak_lost": last > 0 and not info["alive"],
            "next_streak": info["next_streak"], "next_rarity": cc.rarity_for_streak(info["next_streak"]),
        }

    async def history(self, gid: int, uid: int, limit: int = 10) -> list[dict]:
        rows = await self.db.fetchall(
            "SELECT open_id, rarity, source, reward, segment, streak_after, ts FROM chest_opens WHERE guild_id = ? AND user_id = ? ORDER BY ts DESC LIMIT ?",
            (gid, uid, limit),
        )
        return [{"open_id": r["open_id"], "rarity": r["rarity"], "source": r["source"], "reward": r["reward"], "segment": r["segment"],
                 "streak": r["streak_after"], "ts": r["ts"]} for r in rows]

    async def ranking(self, gid: int, limit: int = 10) -> list[dict]:
        rows = await self.db.fetchall(
            "SELECT user_id, streak, best_streak, last_claim FROM chest_state WHERE guild_id = ? AND best_streak > 0 "
            "ORDER BY best_streak DESC, streak DESC LIMIT ?", (gid, limit),
        )
        now = self.clock()
        out = []
        for r in rows:
            alive = r["last_claim"] > 0 and now - r["last_claim"] < cc.STREAK_WINDOW
            out.append({"user_id": r["user_id"], "streak": r["streak"] if alive else 0, "best": r["best_streak"]})
        return out

    async def state(self, gid: int, uid: int) -> dict:
        return {
            "now": self.clock(), "balance": await self._balance(gid, uid), "daily": await self.daily_info(gid, uid),
            "inventory": await self.inventory(gid, uid), "history": await self.history(gid, uid), **await self.public_config(gid),
        }

    # ------------------------------------------------------------------
    # Aperturas
    # ------------------------------------------------------------------
    async def _result(self, row, repeat: bool) -> dict:
        gid, uid = row["guild_id"], row["user_id"]
        return {
            "open_id": row["open_id"], "rarity": row["rarity"], "source": row["source"], "reward": row["reward"], "segment": row["segment"],
            "segment_name": cc.SEGMENT_NAMES[row["segment"]], "streak": row["streak_after"], "ts": row["ts"], "repeat": repeat,
            "balance": await self._balance(gid, uid), "inventory": await self.inventory(gid, uid), "daily": await self.daily_info(gid, uid),
        }

    async def _get_open(self, open_id: str):
        return await self.db.fetchone("SELECT * FROM chest_opens WHERE open_id = ?", (open_id,))

    async def _insert_open(self, open_id, gid, uid, rarity, source, reward, segment, streak_after, prev_claim, ts) -> bool:
        """Inserta la apertura (UNA sentencia atómica). Devuelve False si esa apertura ya existía (reintento)."""
        try:
            await self.db.execute(
                "INSERT INTO chest_opens (open_id, guild_id, user_id, rarity, source, reward, segment, streak_after, prev_claim, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (open_id, gid, uid, rarity, source, reward, segment, streak_after, prev_claim, ts),
            )
            return True
        except sqlite3.IntegrityError as exc:
            msg = str(exc)
            if "chest_opens.open_id" in msg:           # el mismo pedido llegó dos veces
                return False
            if "stale_state" in msg:                   # alguien ya reclamó entre que leímos y escribimos
                info = await self.daily_info(gid, uid)
                raise ChestError("cooldown", "Ya reclamaste tu cofre diario.", ready_at=info["ready_at"]) from exc
            if "no_stock" in msg:
                raise ChestError("no_stock", f"No tenés cofres {cc.RARITY_NAME[rarity].lower()}s para abrir.") from exc
            raise

    async def claim_daily(self, gid: int, uid: int, request_id: str | None = None) -> dict:
        """Reclama el cofre gratuito del día. La racha, el tiempo y el premio los decide SIEMPRE el servidor."""
        open_id = self._key(gid, uid, request_id)
        async with self._locks[(gid, uid)]:
            existing = await self._get_open(open_id)
            if existing:
                return await self._result(existing, repeat=True)
            await self.db.execute("INSERT OR IGNORE INTO chest_state (guild_id, user_id) VALUES (?, ?)", (gid, uid))
            st = await self.db.fetchone("SELECT streak, last_claim FROM chest_state WHERE guild_id = ? AND user_id = ?", (gid, uid))
            now = self.clock()
            info = cc.streak_status(st["last_claim"], st["streak"], now)
            if not info["available"]:
                raise ChestError("cooldown", "Ya reclamaste tu cofre diario.", ready_at=info["ready_at"])
            streak = info["next_streak"]
            rarity = cc.rarity_for_streak(streak)
            settings = await self.settings(gid)
            segment, reward = cc.draw_reward(rarity, settings["scale"], self.rng)
            fresh = await self._insert_open(open_id, gid, uid, rarity, "daily", reward, segment, streak, st["last_claim"], now)
            return await self._result(await self._get_open(open_id), repeat=not fresh)

    async def open_bought(self, gid: int, uid: int, rarity: str, request_id: str | None = None) -> dict:
        """Abre un cofre del inventario. No toca la racha del cofre diario."""
        if rarity not in cc.RARITIES:
            raise ChestError("invalid", "Ese tipo de cofre no existe.")
        open_id = self._key(gid, uid, request_id)
        async with self._locks[(gid, uid)]:
            existing = await self._get_open(open_id)
            if existing:
                return await self._result(existing, repeat=True)
            settings = await self.settings(gid)
            segment, reward = cc.draw_reward(rarity, settings["scale"], self.rng)
            fresh = await self._insert_open(open_id, gid, uid, rarity, "bought", reward, segment, 0, 0.0, self.clock())
            return await self._result(await self._get_open(open_id), repeat=not fresh)

    # ------------------------------------------------------------------
    # Compras
    # ------------------------------------------------------------------
    async def buy(self, gid: int, uid: int, rarity: str, qty: int = 1, request_id: str | None = None) -> dict:
        if rarity not in cc.RARITIES:
            raise ChestError("invalid", "Ese tipo de cofre no existe.")
        if not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= cc.MAX_BUY_QTY:
            raise ChestError("invalid", f"Podés comprar de 1 a {cc.MAX_BUY_QTY} cofres por vez.")
        pid = self._key(gid, uid, request_id)
        async with self._locks[(gid, uid)]:
            existing = await self.db.fetchone("SELECT * FROM chest_purchases WHERE id = ?", (pid,))
            repeat = existing is not None
            if not repeat:
                price = (await self.settings(gid))["prices"][rarity]
                try:
                    await self.db.execute(
                        "INSERT INTO chest_purchases (id, guild_id, user_id, rarity, qty, unit_price, total, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (pid, gid, uid, rarity, qty, price, price * qty, self.clock()),
                    )
                except sqlite3.IntegrityError as exc:
                    if "insufficient_funds" in str(exc):
                        raise ChestError("funds", "No tenés suficientes monedas.", needed=price * qty, balance=await self._balance(gid, uid)) from exc
                    if "chest_purchases.id" not in str(exc):
                        raise
                    repeat = True
                existing = await self.db.fetchone("SELECT * FROM chest_purchases WHERE id = ?", (pid,))
            return {
                "purchase_id": pid, "rarity": existing["rarity"], "qty": existing["qty"], "unit_price": existing["unit_price"], "total": existing["total"],
                "repeat": repeat, "balance": await self._balance(gid, uid), "inventory": await self.inventory(gid, uid),
            }

    # ------------------------------------------------------------------
    # Administración
    # ------------------------------------------------------------------
    async def admin_stats(self, gid: int) -> dict:
        now = self.clock()
        out = {"all": await self._stats_window(gid, 0.0), "week": await self._stats_window(gid, now - 7 * 86400)}
        out["scale"] = (await self.settings(gid))["scale"]
        return out

    async def _stats_window(self, gid: int, since: float) -> dict:
        rows = await self.db.fetchall(
            "SELECT rarity, source, COUNT(*) AS n, COALESCE(SUM(reward), 0) AS coins FROM chest_opens WHERE guild_id = ? AND ts >= ? GROUP BY rarity, source",
            (gid, since),
        )
        buys = await self.db.fetchone(
            "SELECT COALESCE(SUM(qty), 0) AS qty, COALESCE(SUM(total), 0) AS spent FROM chest_purchases WHERE guild_id = ? AND ts >= ?", (gid, since)
        )
        people = await self.db.fetchone("SELECT COUNT(DISTINCT user_id) AS n FROM chest_opens WHERE guild_id = ? AND ts >= ?", (gid, since))
        by_rarity = {r: {"daily": 0, "bought": 0, "coins": 0} for r in cc.RARITIES}
        for r in rows:
            by_rarity[r["rarity"]][r["source"]] += r["n"]
            by_rarity[r["rarity"]]["coins"] += r["coins"]
        paid = sum(v["coins"] for v in by_rarity.values())
        return {
            "opened": sum(v["daily"] + v["bought"] for v in by_rarity.values()), "daily": sum(v["daily"] for v in by_rarity.values()),
            "bought": sum(v["bought"] for v in by_rarity.values()), "paid": paid, "bought_qty": buys["qty"], "spent": buys["spent"],
            "net": paid - buys["spent"], "people": people["n"], "by_rarity": by_rarity,
        }

    async def reset_streak(self, gid: int, uid: int, allow_claim_now: bool = False):
        """Pone la racha en 0. Opcionalmente también habilita reclamar ya (borra el tiempo de espera)."""
        await self.db.execute("INSERT OR IGNORE INTO chest_state (guild_id, user_id) VALUES (?, ?)", (gid, uid))
        if allow_claim_now:
            await self.db.execute("UPDATE chest_state SET streak = 0, last_claim = 0 WHERE guild_id = ? AND user_id = ?", (gid, uid))
        else:
            await self.db.execute("UPDATE chest_state SET streak = 0 WHERE guild_id = ? AND user_id = ?", (gid, uid))
