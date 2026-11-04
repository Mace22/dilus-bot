"""Panel de Admin: acciones y registro. Solo para quienes tienen el permiso de Administrador en Discord.

El permiso se revisa en CADA pedido contra Discord (no se confía en lo que diga el navegador).
"""
import datetime
import logging
import time

import discord

from cogs.warns import AUTO_TIMEOUT_MIN, WARN_LIMIT
from utils import adminlog
from web.common import ApiError

log = logging.getLogger("dilus-bot.web.admin")

COINS_MAX = 10_000_000       # tope por operación
TIMEOUT_MAX = 40320          # 28 días, el máximo de Discord
MOD_ACTIONS = {"warn", "clearwarns", "timeout", "untimeout", "kick", "ban"}


class Admin:
    def __init__(self, svc):
        self.svc = svc

    # ------------------------------------------------------------------
    # Permisos
    # ------------------------------------------------------------------
    async def is_admin(self, gid: int, uid: int) -> bool:
        guild = self.svc.bot.get_guild(gid)
        if guild is None:
            return False
        member = await self.svc.member(guild, uid)
        return bool(member and member.guild_permissions.administrator)

    async def _actor(self, gid: int, uid: int):
        guild = self.svc.guild(gid)
        member = await self.svc.member(guild, uid)
        if member is None or not member.guild_permissions.administrator:
            raise ApiError("Esta sección es solo para administradores del servidor.", 403)
        return guild, member

    async def _target(self, guild: discord.Guild, raw, *, allow_bot: bool = False) -> discord.Member:
        if not isinstance(raw, str) or not raw.isdigit():
            raise ApiError("Elegí a una persona.")
        member = await self.svc.member(guild, int(raw))
        if member is None:
            raise ApiError("No encuentro a esa persona en el servidor.", 404)
        if member.bot and not allow_bot:
            raise ApiError("No se puede hacer eso con un bot.")
        return member

    @staticmethod
    def _check_hierarchy(guild: discord.Guild, actor: discord.Member, target: discord.Member):
        if target.id == actor.id:
            raise ApiError("No podés hacerte eso a vos mismo.")
        if target.id == guild.owner_id:
            raise ApiError("No se puede actuar sobre el dueño del servidor.", 409)
        if actor.id != guild.owner_id and target.top_role >= actor.top_role:
            raise ApiError("Esa persona tiene un rol igual o superior al tuyo.", 409)
        if target.top_role >= guild.me.top_role:
            raise ApiError("Esa persona tiene un rol igual o superior al mío.", 409)

    @staticmethod
    def _reason(raw) -> str:
        return raw.strip()[:200] if isinstance(raw, str) else ""

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    async def overview(self, gid: int, uid: int) -> dict:
        guild, _ = await self._actor(gid, uid)
        db = self.svc.db
        eco = await db.fetchone("SELECT COALESCE(SUM(balance), 0) AS total, COUNT(*) AS players FROM economy WHERE guild_id = ?", (gid,))
        warns = await db.fetchone("SELECT COUNT(*) AS c FROM warns WHERE guild_id = ?", (gid,))
        day = await db.fetchone("SELECT COUNT(*) AS c FROM admin_log WHERE guild_id = ? AND ts > ?", (gid, time.time() - 86400))
        given = await db.fetchone(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM admin_log WHERE guild_id = ? AND action = 'coins_give' AND ts > ?", (gid, time.time() - 86400)
        )
        return {
            "members": guild.member_count, "coins": eco["total"], "players": eco["players"],
            "warns": warns["c"], "actions_24h": day["c"], "given_24h": given["s"],
            "warn_limit": WARN_LIMIT, "auto_timeout": AUTO_TIMEOUT_MIN,
            "limits": {"coins_max": COINS_MAX, "timeout_max": TIMEOUT_MAX},
        }

    async def members(self, gid: int, uid: int, query) -> dict:
        guild, _ = await self._actor(gid, uid)
        q = str(query or "").strip().lower()[:32]
        if not q:
            return {"members": []}
        found = []
        for m in guild.members:
            if m.bot:
                continue
            name = m.display_name.lower()
            if q in name or q in m.name.lower():
                found.append((0 if name.startswith(q) else 1, name, m))
        found.sort(key=lambda t: (t[0], t[1]))
        out = []
        for _, _, m in found[:8]:
            bal = await self.svc.db.fetchone("SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?", (gid, m.id))
            wc = await self.svc.db.fetchone("SELECT COUNT(*) AS c FROM warns WHERE guild_id = ? AND user_id = ?", (gid, m.id))
            out.append({
                "id": str(m.id), "name": m.display_name, "avatar": str(m.display_avatar.with_size(64)),
                "balance": bal["balance"] if bal else 0, "warns": wc["c"],
                "timed_out": bool(m.timed_out_until and m.timed_out_until > discord.utils.utcnow()),
            })
        return {"members": out}

    async def logs(self, gid: int, uid: int, kind) -> dict:
        await self._actor(gid, uid)
        if kind in ("economy", "moderation"):
            acts = adminlog.actions_in(kind)
            marks = ",".join("?" * len(acts))
            rows = await self.svc.db.fetchall(
                f"SELECT * FROM admin_log WHERE guild_id = ? AND action IN ({marks}) ORDER BY id DESC LIMIT 100", (gid, *acts)
            )
        else:
            kind = "all"
            rows = await self.svc.db.fetchall("SELECT * FROM admin_log WHERE guild_id = ? ORDER BY id DESC LIMIT 100", (gid,))
        items = []
        for r in rows:
            title, emoji, cat = adminlog.ACTIONS.get(r["action"], (r["action"], "🛠️", "other"))
            items.append({
                "id": r["id"], "action": r["action"], "title": title, "emoji": emoji, "category": cat,
                "actor": r["actor_name"], "actor_id": str(r["actor_id"]),
                "target": r["target_name"], "amount": r["amount"], "detail": r["detail"], "source": r["source"], "ts": r["ts"],
            })
        return {"kind": kind, "items": items}

    # ------------------------------------------------------------------
    # Economía: dar / quitar monedas
    # ------------------------------------------------------------------
    async def coins(self, gid: int, uid: int, target, amount, reason) -> dict:
        guild, actor = await self._actor(gid, uid)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount == 0 or abs(amount) > COINS_MAX:
            raise ApiError(f"El monto tiene que ser un número entero distinto de 0 (máximo {COINS_MAX} por operación).")
        member = await self._target(guild, target)
        reason = self._reason(reason)
        async with self.svc._locks[(gid, member.id)]:
            if not await self.svc.eco.add(gid, member.id, amount):
                raise ApiError("Esa persona no tiene tantas monedas para quitar.", 409)
            balance = await self.svc.eco.balance(gid, member.id)
        await adminlog.record(
            self.svc.bot, guild, actor=actor, action="coins_give" if amount > 0 else "coins_take",
            target=member, amount=amount, detail=reason, source="web",
        )
        return {"target": member.display_name, "amount": amount, "balance": balance}

    # ------------------------------------------------------------------
    # Moderación
    # ------------------------------------------------------------------
    async def moderate(self, gid: int, uid: int, action, target, reason, minutes) -> dict:
        guild, actor = await self._actor(gid, uid)
        if action not in MOD_ACTIONS:
            raise ApiError("Acción inválida.")
        member = await self._target(guild, target)
        self._check_hierarchy(guild, actor, member)
        reason = self._reason(reason)
        audit = f"{actor} (panel web) — {reason or 'Sin razón'}"
        detail, text = reason, ""
        try:
            if action == "warn":
                if not reason:
                    raise ApiError("Para advertir tenés que escribir una razón.")
                await self.svc.db.execute(
                    "INSERT INTO warns (guild_id, user_id, moderator_id, reason, created) VALUES (?, ?, ?, ?, ?)",
                    (gid, member.id, actor.id, reason, time.time()),
                )
                count = (await self.svc.db.fetchone("SELECT COUNT(*) AS c FROM warns WHERE guild_id = ? AND user_id = ?", (gid, member.id)))["c"]
                text = f"{member.display_name} fue advertido ({count}/{WARN_LIMIT})."
                detail = f"{reason} ({count}/{WARN_LIMIT})"
                if count >= WARN_LIMIT:
                    try:
                        await member.timeout(datetime.timedelta(minutes=AUTO_TIMEOUT_MIN), reason=f"{WARN_LIMIT} advertencias")
                        text += f" Llegó al límite: timeout automático de {AUTO_TIMEOUT_MIN} min."
                    except discord.HTTPException:
                        text += " No pude aplicarle el timeout automático."
                try:
                    await member.send(f"⚠️ Recibiste una advertencia en **{guild.name}** ({count}/{WARN_LIMIT}).\nRazón: {reason}")
                except discord.HTTPException:
                    pass
            elif action == "clearwarns":
                cur = await self.svc.db.execute("DELETE FROM warns WHERE guild_id = ? AND user_id = ?", (gid, member.id))
                text = f"Borré {cur.rowcount} advertencia(s) de {member.display_name}."
                detail = f"{reason} ({cur.rowcount} borradas)".strip()
            elif action == "timeout":
                if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= TIMEOUT_MAX:
                    raise ApiError(f"Los minutos tienen que estar entre 1 y {TIMEOUT_MAX}.")
                await member.timeout(datetime.timedelta(minutes=minutes), reason=audit)
                text = f"{member.display_name} quedó en timeout por {minutes} min."
                detail = f"{minutes} min" + (f" — {reason}" if reason else "")
            elif action == "untimeout":
                await member.timeout(None, reason=audit)
                text = f"Le quité el timeout a {member.display_name}."
            elif action == "kick":
                await member.kick(reason=audit)
                text = f"{member.display_name} fue expulsado."
            elif action == "ban":
                await member.ban(reason=audit, delete_message_days=0)
                text = f"{member.display_name} fue baneado."
        except discord.Forbidden:
            raise ApiError("No tengo permisos para hacer eso. Revisá que mi rol esté por encima y tenga el permiso necesario.", 409)
        except discord.HTTPException:
            raise ApiError("Discord rechazó la acción. Probá de nuevo.", 502)

        await adminlog.record(self.svc.bot, guild, actor=actor, action=action, target=member, detail=detail, source="web")
        return {"message": text}
