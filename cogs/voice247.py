import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.embeds import error, ok

log = logging.getLogger("dilus-bot.voice")

VoiceLike = discord.VoiceChannel | discord.StageChannel


class Voice247(commands.Cog):
    """El bot entra a un canal de voz (silenciado y ensordecido) y se queda ahí para siempre.

    Si se cae la conexión, lo mueven o lo desconectan, vuelve solo.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def cog_load(self):
        self.keepalive.start()

    async def cog_unload(self):
        self.keepalive.cancel()

    # ------------------------------------------------------------------
    # Lógica de conexión
    # ------------------------------------------------------------------
    async def ensure_connected(self, guild: discord.Guild, channel_id: int):
        async with self._lock(guild.id):
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                return

            perms = channel.permissions_for(guild.me)
            if not (perms.view_channel and perms.connect):
                log.warning("Sin permisos para entrar a #%s en %s", channel.name, guild.name)
                return

            vc = guild.voice_client
            if vc is not None and vc.is_connected():
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
                me = guild.me
                if not me.voice or not (me.voice.self_mute and me.voice.self_deaf):
                    await guild.change_voice_state(channel=channel, self_mute=True, self_deaf=True)
                return

            # Conexión zombie: limpiar antes de reconectar
            if vc is not None:
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass

            await channel.connect(self_mute=True, self_deaf=True, reconnect=True, timeout=30)
            log.info("Conectado a #%s en %s", channel.name, guild.name)

    @tasks.loop(seconds=30)
    async def keepalive(self):
        rows = await self.bot.db.fetchall("SELECT guild_id, voice_channel FROM guild_settings WHERE voice_channel IS NOT NULL")
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
            try:
                await self.ensure_connected(guild, row["voice_channel"])
            except Exception:
                log.exception("Fallo al reconectar en %s", guild.name)

    @keepalive.before_loop
    async def _before_keepalive(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Si desconectan o mueven al bot, vuelve rápido sin esperar al ciclo de 30s
        if member.id != self.bot.user.id or before.channel is None:
            return
        target = await self.bot.db.get_setting(member.guild.id, "voice_channel")
        if not target:
            return
        if after.channel is None or after.channel.id != target:
            await asyncio.sleep(3)
            try:
                await self.ensure_connected(member.guild, target)
            except Exception:
                log.exception("Fallo al volver al canal en %s", member.guild.name)

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------
    @app_commands.command(name="entrar", description="El bot entra a tu canal de voz (silenciado) y se queda 24/7")
    @app_commands.describe(canal="Canal de voz (por defecto, el canal donde estás conectado)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def entrar(self, interaction: discord.Interaction, canal: discord.VoiceChannel | discord.StageChannel | None = None):
        target = canal
        if target is None:
            voice = getattr(interaction.user, "voice", None)
            target = voice.channel if voice else None
        if target is None:
            return await interaction.response.send_message(
                embed=error("Conectate a un canal de voz primero o elegí uno en el parámetro `canal`."), ephemeral=True
            )

        perms = target.permissions_for(interaction.guild.me)
        if not (perms.view_channel and perms.connect):
            return await interaction.response.send_message(
                embed=error(f"No tengo permiso para ver o conectarme a {target.mention}."), ephemeral=True
            )

        await interaction.response.defer()
        await self.bot.db.set_setting(interaction.guild_id, "voice_channel", target.id)
        try:
            await self.ensure_connected(interaction.guild, target.id)
        except Exception:
            log.exception("No se pudo conectar")
            return await interaction.followup.send(
                embed=error("No pude conectarme. Revisá mis permisos y probá de nuevo.")
            )
        await interaction.followup.send(
            embed=ok(f"Entré a {target.mention} silenciado y ensordecido. Me quedo acá 24/7 (si me sacan, vuelvo).")
        )

    @app_commands.command(name="salir", description="El bot sale del canal de voz y deja de reconectarse")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def salir(self, interaction: discord.Interaction):
        await self.bot.db.set_setting(interaction.guild_id, "voice_channel", None)
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect(force=True)
            return await interaction.response.send_message(embed=ok("Salí del canal de voz."))
        await interaction.response.send_message(embed=ok("Ya no estaba en ningún canal, pero desactivé la reconexión."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice247(bot))
