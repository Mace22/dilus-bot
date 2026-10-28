import asyncio
import logging
import os
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.embeds import error, ok

log = logging.getLogger("dilus-bot.voice")

# ---------------------------------------------------------------------------
# VOICE_MODE (variable de entorno, opcional)
#   presence (por defecto): el bot figura dentro del canal usando solo su conexión principal con
#       Discord. NO abre el enlace de audio, que es justo lo que se cortaba en tus logs
#       ("Disconnected from voice", "Could not connect to voice").
#   real: abre la conexión de voz completa (como antes). Usalo solo si "presence" no te funciona.
# ---------------------------------------------------------------------------
MODE = os.getenv("VOICE_MODE", "presence").strip().lower()
if MODE not in ("presence", "real"):
    MODE = "presence"

CHECK_SECONDS = 20                              # cada cuánto se revisa que el bot siga en el canal
MISSES_BEFORE_REJOIN = 2 if MODE == "presence" else 3   # revisiones seguidas "afuera" antes de volver
MIN_REJOIN_INTERVAL = 30                        # nunca intenta volver más de 1 vez cada 30 s


class Voice247(commands.Cog):
    """Mantiene al bot en un canal de voz, silenciado y ensordecido, y lo devuelve si algo lo saca.

    /entrar lo deja configurado (queda guardado, así que también vuelve solo tras reiniciar el bot)
    y /salir lo desactiva.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}
        self._misses: dict[int, int] = {}
        self._last_join: dict[int, float] = {}

    async def cog_load(self):
        self.watchdog.start()
        log.info("Voz 24/7 en modo '%s'", MODE)

    async def cog_unload(self):
        self.watchdog.cancel()

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    # ------------------------------------------------------------------
    # Estado y conexión
    # ------------------------------------------------------------------
    def _in_channel(self, guild: discord.Guild, channel_id: int) -> bool:
        if MODE == "real":
            vc = guild.voice_client
            return bool(vc and vc.is_connected() and vc.channel and vc.channel.id == channel_id)
        me = guild.me
        return bool(me and me.voice and me.voice.channel and me.voice.channel.id == channel_id)

    async def join(self, guild: discord.Guild, channel: discord.VoiceChannel | discord.StageChannel):
        async with self._lock(guild.id):
            self._last_join[guild.id] = time.time()
            vc = guild.voice_client

            if MODE == "real":
                if vc is not None and vc.is_connected():
                    if vc.channel.id != channel.id:
                        await vc.move_to(channel)
                        await guild.change_voice_state(channel=channel, self_mute=True, self_deaf=True)
                    return
                if vc is not None:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
                await channel.connect(self_mute=True, self_deaf=True, reconnect=True, timeout=30)
            else:
                # Modo presencia: una sola orden por la conexión principal, sin enlace de audio.
                if vc is not None:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
                await guild.change_voice_state(channel=channel, self_mute=True, self_deaf=True)

            log.info("Unido a #%s en %s (modo %s)", channel.name, guild.name, MODE)

    async def leave(self, guild: discord.Guild):
        async with self._lock(guild.id):
            vc = guild.voice_client
            if vc is not None:
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
            me = guild.me
            if me and me.voice and me.voice.channel:
                await guild.change_voice_state(channel=None)

    # ------------------------------------------------------------------
    # Vigilante: solo actúa si el bot realmente quedó afuera varias revisiones seguidas
    # ------------------------------------------------------------------
    @tasks.loop(seconds=CHECK_SECONDS)
    async def watchdog(self):
        rows = await self.bot.db.fetchall(
            "SELECT guild_id, voice_channel FROM guild_settings WHERE voice_channel IS NOT NULL"
        )
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue
            gid, channel_id = guild.id, row["voice_channel"]

            if self._in_channel(guild, channel_id):
                self._misses[gid] = 0
                continue

            if gid in self._misses:
                misses = self._misses[gid] + 1
            else:
                misses = MISSES_BEFORE_REJOIN  # primera revisión tras arrancar el bot: volver enseguida
            self._misses[gid] = misses
            if misses < MISSES_BEFORE_REJOIN:
                continue
            if time.time() - self._last_join.get(gid, 0) < MIN_REJOIN_INTERVAL:
                continue

            channel = guild.get_channel(channel_id)
            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                continue
            perms = channel.permissions_for(guild.me)
            if not (perms.view_channel and perms.connect):
                continue
            try:
                await self.join(guild, channel)
                self._misses[gid] = 0
                log.info("El bot estaba afuera de #%s en %s: volvió a unirse", channel.name, guild.name)
            except Exception:
                log.exception("No pude volver a unirme a #%s en %s", channel.name, guild.name)

    @watchdog.before_loop
    async def _before_watchdog(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------
    @app_commands.command(name="entrar", description="El bot entra a tu canal de voz (silenciado) y se queda siempre")
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
        self._misses[interaction.guild_id] = 0
        try:
            await self.join(interaction.guild, target)
        except Exception:
            log.exception("No se pudo unir a la voz")
            return await interaction.followup.send(
                embed=error("No pude entrar ahora. Quedó guardado y voy a reintentar solo en unos segundos.")
            )
        await interaction.followup.send(
            embed=ok(f"Entré a {target.mention} silenciado y ensordecido. Me quedo acá y, si algo me saca, vuelvo solo. (`/salir` para que me vaya)")
        )

    @app_commands.command(name="salir", description="El bot sale del canal de voz y deja de volver")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def salir(self, interaction: discord.Interaction):
        await self.bot.db.set_setting(interaction.guild_id, "voice_channel", None)
        self._misses.pop(interaction.guild_id, None)
        await self.leave(interaction.guild)
        await interaction.response.send_message(embed=ok("Salí del canal de voz y no voy a volver hasta el próximo `/entrar`."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice247(bot))
