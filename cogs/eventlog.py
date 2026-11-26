"""Escucha lo que pasa en el servidor y lo guarda para el panel web (ver utils/eventlog.py)."""
import discord
from discord.ext import commands

from utils import eventlog as ev

NO_ROLES = "Sin roles"
CHANNEL_KINDS = {
    discord.ChannelType.text: "texto", discord.ChannelType.category: "categoría",
    discord.ChannelType.news: "anuncios", discord.ChannelType.forum: "foro",
}


def is_voice(channel) -> bool:
    # los canales de voz se ignoran: los "lobby" temporales los crean y borran todo el tiempo
    return isinstance(channel, (discord.VoiceChannel, discord.StageChannel))


class EventLog(commands.Cog):
    """Registro de eventos para el panel web."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def rec(self, guild: discord.Guild, kind: str, **kw):
        await ev.record(self.bot, guild.id, kind, **kw)

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
        await self.rec(member.guild, "member_leave", user=member, detail=detail)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self.rec(guild, "member_ban", user=user)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await self.rec(guild, "member_unban", user=user)

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
            await self.rec(g, "nick_update", user=after, detail=f"{old} → {new}", before=old, after=new)
        if before.guild_avatar != after.guild_avatar:
            await self.rec(
                g, "guild_avatar_update", user=after,
                detail="Nuevo avatar del servidor" if after.guild_avatar else "Quitó su avatar del servidor",
                img=str(after.display_avatar.url), old_img=str(before.display_avatar.url),
            )

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if after.bot:
            return
        guilds = [g for g in self.bot.guilds if g.get_member(after.id)]
        if before.avatar != after.avatar:
            for g in guilds:
                await self.rec(g, "avatar_update", user=after, detail="Nuevo avatar",
                               img=str(after.display_avatar.url), old_img=str(before.display_avatar.url))
        for attr, label in (("name", "usuario"), ("global_name", "nombre")):
            old, new = getattr(before, attr, None), getattr(after, attr, None)
            if old != new:
                for g in guilds:
                    await self.rec(g, "name_update", user=after, detail=f"{label}: {old or '—'} → {new or '—'}",
                                   before=old or "—", after=new or "—")

    # ---- mensajes ----
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
        await self.rec(messages[0].guild, "bulk_delete", channel=messages[0].channel, detail=f"{len(messages)} mensajes")

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
        if not is_voice(channel):
            await self.rec(channel.guild, "channel_create", channel=channel, detail=CHANNEL_KINDS.get(channel.type, str(channel.type)))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not is_voice(channel):
            await self.rec(channel.guild, "channel_delete", channel=channel, detail=CHANNEL_KINDS.get(channel.type, str(channel.type)))

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if not is_voice(after) and before.name != after.name:
            await self.rec(after.guild, "channel_update", channel=after, detail=f"#{before.name} → #{after.name}",
                           before=before.name, after=after.name)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self.rec(role.guild, "role_create", detail=role.name)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self.rec(role.guild, "role_delete", detail=role.name)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventLog(bot))
