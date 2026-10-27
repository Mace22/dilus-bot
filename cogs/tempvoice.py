import logging
import time

import discord
from discord.ext import commands, tasks

log = logging.getLogger("dilus-bot.tempvoice")


class TempVoice(commands.Cog):
    """Canales de voz temporales: entrás al canal 'lobby' y el bot te crea uno propio.

    Se configura con /config tempvoice. El canal se borra solo cuando queda vacío.
    La persona que lo creó puede renombrarlo y ponerle límite de usuarios desde los ajustes del canal.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldown: dict[int, float] = {}

    async def cog_load(self):
        self.cleanup.start()

    async def cog_unload(self):
        self.cleanup.cancel()

    async def _is_temp(self, channel_id: int) -> bool:
        row = await self.bot.db.fetchone("SELECT 1 FROM temp_voice WHERE channel_id = ?", (channel_id,))
        return row is not None

    async def _drop(self, channel: discord.abc.GuildChannel | None, channel_id: int):
        await self.bot.db.execute("DELETE FROM temp_voice WHERE channel_id = ?", (channel_id,))
        if channel:
            try:
                await channel.delete(reason="Canal temporal vacío - Dilu's Bot")
            except discord.HTTPException:
                pass

    async def _create(self, member: discord.Member, lobby: discord.VoiceChannel):
        now = time.time()
        if now - self._cooldown.get(member.id, 0) < 8:
            return
        self._cooldown[member.id] = now

        guild = member.guild
        perms = guild.me.guild_permissions
        if not (perms.manage_channels and perms.move_members):
            log.warning("Faltan permisos (Gestionar canales / Mover miembros) para crear canales temporales en %s", guild.name)
            return

        overwrites = {
            member: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, move_members=True),
        }
        try:
            channel = await guild.create_voice_channel(
                name=f"🔊 {member.display_name}"[:100],
                category=lobby.category,
                overwrites=overwrites,
                reason=f"Canal temporal de {member}",
            )
        except discord.HTTPException:
            log.exception("No pude crear el canal temporal")
            return

        await self.bot.db.execute(
            "INSERT OR REPLACE INTO temp_voice (channel_id, guild_id, owner_id) VALUES (?, ?, ?)",
            (channel.id, guild.id, member.id),
        )
        try:
            await member.move_to(channel)
        except discord.HTTPException:
            # La persona se fue antes de poder moverla: no dejar el canal huérfano
            await self._drop(channel, channel.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        if after.channel is not None and after.channel != before.channel:
            lobby_id = await self.bot.db.get_setting(member.guild.id, "tempvoice_channel")
            if lobby_id and after.channel.id == lobby_id and isinstance(after.channel, discord.VoiceChannel):
                await self._create(member, after.channel)

        if before.channel is not None and before.channel != after.channel:
            if len(before.channel.members) == 0 and await self._is_temp(before.channel.id):
                await self._drop(before.channel, before.channel.id)

    @tasks.loop(minutes=5)
    async def cleanup(self):
        """Red de seguridad: borra canales temporales vacíos o que ya no existen (p. ej. tras reiniciar el bot)."""
        rows = await self.bot.db.fetchall("SELECT channel_id, guild_id FROM temp_voice")
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue
            channel = guild.get_channel(row["channel_id"])
            if channel is None:
                await self.bot.db.execute("DELETE FROM temp_voice WHERE channel_id = ?", (row["channel_id"],))
            elif (
                isinstance(channel, discord.VoiceChannel)
                and len(channel.members) == 0
                and (discord.utils.utcnow() - channel.created_at).total_seconds() > 30
            ):
                await self._drop(channel, channel.id)

    @cleanup.before_loop
    async def _before_cleanup(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TempVoice(bot))
