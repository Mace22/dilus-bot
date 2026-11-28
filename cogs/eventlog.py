"""Escucha lo que pasa en el servidor: lo guarda para el panel web (utils/eventlog.py) y, para los cambios
importantes que cogs/warns.py no avisa, lo manda también al canal de logs de Discord (`/config logs`)."""
import discord
from discord.ext import commands

from utils import eventlog as ev
from utils.embeds import make_embed

RED, GREEN, ORANGE, BLUE, GREY = 0xEF4444, 0x22C55E, 0xF59E0B, 0x3B82F6, 0x6B7280
NO_ROLES = "Sin roles"
CHANNEL_KINDS = {
    discord.ChannelType.text: "texto", discord.ChannelType.category: "categoría",
    discord.ChannelType.news: "anuncios", discord.ChannelType.forum: "foro",
}


def is_voice(channel) -> bool:
    # los canales de voz se ignoran: los "lobby" temporales los crean y borran todo el tiempo
    return isinstance(channel, (discord.VoiceChannel, discord.StageChannel))


def who(user) -> str:
    return f"{user.mention} ({user})"


def before_after(title: str, user, old: str, new: str, color: int = BLUE) -> discord.Embed:
    embed = make_embed(title, who(user), color=color)
    embed.add_field(name="Antes", value=ev.clip(old, 500) or "—", inline=False)
    embed.add_field(name="Después", value=ev.clip(new, 500) or "—", inline=False)
    return embed


def avatar_embed(title: str, user, old_url: str, new_url: str) -> discord.Embed:
    """Avatar viejo en la miniatura (arriba a la derecha) y el nuevo grande abajo."""
    embed = make_embed(title, who(user), color=BLUE)
    embed.set_thumbnail(url=old_url)
    embed.set_image(url=new_url)
    embed.add_field(name="Antes", value=f"[ver avatar viejo]({old_url})")
    embed.add_field(name="Ahora", value=f"[ver avatar nuevo]({new_url})")
    return embed


def role_changes(before: discord.Role, after: discord.Role) -> list[str]:
    out = []
    if before.name != after.name:
        out.append(f"nombre: {before.name} → {after.name}")
    if before.color != after.color:
        out.append(f"color: {before.color} → {after.color}")
    if before.hoist != after.hoist:
        out.append(f"mostrar separado: {'sí' if after.hoist else 'no'}")
    gained = [n.replace("_", " ") for n, v in after.permissions if v and not getattr(before.permissions, n)]
    lost = [n.replace("_", " ") for n, v in after.permissions if not v and getattr(before.permissions, n)]
    if gained:
        out.append("permisos agregados: " + ", ".join(gained))
    if lost:
        out.append("permisos quitados: " + ", ".join(lost))
    return out


def audit_fields(entry) -> dict:
    """Quién hizo la acción y por qué, para guardarlo en el registro."""
    if entry is None:
        return {}
    return {"by": ev.name_of(entry.user), "reason": entry.reason}


class EventLog(commands.Cog):
    """Registro de eventos para el panel web y el canal de logs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def rec(self, guild: discord.Guild, kind: str, *, log: discord.Embed | None = None, **kw):
        await ev.record(self.bot, guild.id, kind, **kw)
        if log is not None:
            await ev.post_log(self.bot, guild, log)

    # ---- miembros ----
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        detail = f"Cuenta creada el {member.created_at:%d/%m/%Y}"
        if (discord.utils.utcnow() - member.created_at).days < 7:
            detail += " · ⚠️ cuenta de menos de 7 días"
        await self.rec(member.guild, "member_join", user=member, detail=detail, img=str(member.display_avatar.url))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        roles = ", ".join(r.name for r in member.roles if not r.is_default()) or NO_ROLES
        detail = f"Roles: {roles}"
        if member.joined_at:
            detail = f"Estuvo desde el {member.joined_at:%d/%m/%Y} · {detail}"
        kick = await ev.audit_entry(member.guild, discord.AuditLogAction.kick, member.id)
        if kick:   # no se fue solo: lo expulsaron
            await self.rec(member.guild, "member_kick", user=member, detail=detail, **audit_fields(kick))
        else:
            await self.rec(member.guild, "member_leave", user=member, detail=detail)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        entry = await ev.audit_entry(guild, discord.AuditLogAction.ban, user.id)
        await self.rec(guild, "member_ban", user=user, **audit_fields(entry))

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        entry = await ev.audit_entry(guild, discord.AuditLogAction.unban, user.id)
        await self.rec(guild, "member_unban", user=user, **audit_fields(entry))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
        g = after.guild
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until and after.timed_out_until > discord.utils.utcnow():
                await self.rec(g, "timeout_on", user=after, detail=f"Hasta el {after.timed_out_until:%d/%m/%Y %H:%M} UTC")
            else:
                await self.rec(g, "timeout_off", user=after)

        before_ids, after_ids = {r.id for r in before.roles}, {r.id for r in after.roles}
        added = [r.name for r in after.roles if r.id not in before_ids]
        removed = [r.name for r in before.roles if r.id not in after_ids]
        if added:
            await self.rec(g, "role_add", user=after, detail=", ".join(added))
        if removed:
            await self.rec(g, "role_remove", user=after, detail=", ".join(removed))

        if before.nick != after.nick:
            old, new = before.nick or "(sin apodo)", after.nick or "(sin apodo)"
            await self.rec(g, "nick_update", user=after, detail=f"{old} → {new}", before=old, after=new,
                           log=before_after("📝 Cambió su apodo", after, old, new))
        if before.guild_avatar != after.guild_avatar:
            old_url, new_url = str(before.display_avatar.url), str(after.display_avatar.url)
            await self.rec(
                g, "guild_avatar_update", user=after,
                detail="Nuevo avatar del servidor" if after.guild_avatar else "Quitó su avatar del servidor",
                img=new_url, old_img=old_url, log=avatar_embed("🖼️ Cambió su avatar del servidor", after, old_url, new_url),
            )

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if after.bot:
            return
        guilds = [g for g in self.bot.guilds if g.get_member(after.id)]
        if before.avatar != after.avatar:
            old_url, new_url = str(before.display_avatar.url), str(after.display_avatar.url)
            for g in guilds:
                await self.rec(g, "avatar_update", user=after, detail="Nuevo avatar", img=new_url, old_img=old_url,
                               log=avatar_embed("🖼️ Cambió su avatar", after, old_url, new_url))
        for attr, label in (("name", "usuario"), ("global_name", "nombre")):
            old, new = getattr(before, attr, None), getattr(after, attr, None)
            if old != new:
                for g in guilds:
                    await self.rec(g, "name_update", user=after, detail=f"{label}: {old or '—'} → {new or '—'}",
                                   before=old or "—", after=new or "—",
                                   log=before_after(f"📝 Cambió su nombre de {label}", after, old or "—", new or "—"))

    # ---- mensajes (el canal de Discord ya lo avisa cogs/warns.py: acá solo se guarda para el panel) ----
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot or (not message.content and not message.attachments):
            return
        await self.rec(message.guild, "message_delete", user=message.author, channel=message.channel,
                       detail=message.content, attachments=len(message.attachments) or None)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        await self.rec(before.guild, "message_edit", user=before.author, channel=before.channel,
                       detail=after.content, before=before.content, after=after.content)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages or not messages[0].guild:
            return
        channel = messages[0].channel
        embed = make_embed("🧹 Borrado masivo de mensajes", f"{len(messages)} mensajes en {channel.mention}", color=RED)
        await self.rec(messages[0].guild, "bulk_delete", channel=channel, detail=f"{len(messages)} mensajes", log=embed)

    # ---- voz ----
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or before.channel == after.channel:
            return
        g = member.guild
        if before.channel is None:
            await self.rec(g, "voice_join", user=member, channel=after.channel)
        elif after.channel is None:
            await self.rec(g, "voice_leave", user=member, channel=before.channel)
        else:
            await self.rec(g, "voice_move", user=member, channel=after.channel,
                           detail=f"{before.channel.name} → {after.channel.name}")

    # ---- servidor ----
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if is_voice(channel):
            return
        kind = CHANNEL_KINDS.get(channel.type, str(channel.type))
        embed = make_embed("➕ Canal creado", f"{channel.mention} ({kind})", color=GREEN)
        await self.rec(channel.guild, "channel_create", channel=channel, detail=kind, log=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if is_voice(channel):
            return
        kind = CHANNEL_KINDS.get(channel.type, str(channel.type))
        entry = await ev.audit_entry(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        embed = make_embed("➖ Canal borrado", f"#{channel.name} ({kind})", color=RED)
        if entry:
            embed.add_field(name="Por", value=entry.user.mention)
        await self.rec(channel.guild, "channel_delete", channel=channel, detail=kind, log=embed, **audit_fields(entry))

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if is_voice(after) or before.name == after.name:
            return
        embed = make_embed("🛠️ Canal renombrado", after.mention, color=BLUE)
        embed.add_field(name="Antes", value=f"#{before.name}")
        embed.add_field(name="Después", value=f"#{after.name}")
        await self.rec(after.guild, "channel_update", channel=after, detail=f"#{before.name} → #{after.name}",
                       before=before.name, after=after.name, log=embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self.rec(role.guild, "role_create", detail=role.name, log=make_embed("🆕 Rol creado", role.mention, color=GREEN))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        entry = await ev.audit_entry(role.guild, discord.AuditLogAction.role_delete, role.id)
        embed = make_embed("❌ Rol borrado", role.name, color=RED)
        if entry:
            embed.add_field(name="Por", value=entry.user.mention)
        await self.rec(role.guild, "role_delete", detail=role.name, log=embed, **audit_fields(entry))

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = role_changes(before, after)
        if not changes:   # por ejemplo, solo cambió de posición en la lista
            return
        embed = make_embed("🛠️ Rol modificado", after.mention, color=ORANGE)
        embed.add_field(name="Cambios", value=ev.clip("\n".join(changes), 1000), inline=False)
        await self.rec(after.guild, "role_update", detail=f"{after.name}: " + "; ".join(changes), log=embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if not invite.guild:
            return
        by = ev.name_of(invite.inviter) if invite.inviter else None
        uses = "∞" if not invite.max_uses else str(invite.max_uses)
        channel = invite.channel if hasattr(invite.channel, "name") else None
        embed = make_embed("🔗 Invitación creada", f"`{invite.code}`" + (f" por {invite.inviter.mention}" if invite.inviter else ""), color=GREEN)
        embed.add_field(name="Usos máximos", value=uses)
        await self.rec(invite.guild, "invite_create", user=invite.inviter, channel=channel,
                       detail=f"{invite.code} · usos máximos: {uses}", by=by, log=embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if not invite.guild:
            return
        await self.rec(invite.guild, "invite_delete", detail=invite.code,
                       log=make_embed("🔗 Invitación borrada", f"`{invite.code}`", color=GREY))


async def setup(bot: commands.Bot):
    await bot.add_cog(EventLog(bot))
