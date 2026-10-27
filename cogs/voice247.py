import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import error, ok

log = logging.getLogger("dilus-bot.voice")


class Voice247(commands.Cog):
    """El bot entra a un canal de voz silenciado y ensordecido y se queda ahí.

    Es 100% manual: si se desconecta o lo sacan, hay que volver a ejecutar /entrar.
    (La librería solo reintenta sola ante cortes de red momentáneos, nunca después de un /salir
    ni si un admin lo desconecta a mano.)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def join(self, guild: discord.Guild, channel: discord.VoiceChannel | discord.StageChannel):
        async with self._lock(guild.id):
            vc = guild.voice_client

            if vc is not None and vc.is_connected():
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
                    # move_to puede resetear el estado de mute/deaf, así que se vuelve a marcar una sola vez
                    await guild.change_voice_state(channel=channel, self_mute=True, self_deaf=True)
                return

            # Conexión a medias o "zombie": limpiarla antes de entrar de nuevo
            if vc is not None:
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass

            await channel.connect(self_mute=True, self_deaf=True, reconnect=True, timeout=30)
            log.info("Conectado a #%s en %s", channel.name, guild.name)

    @app_commands.command(name="entrar", description="El bot entra a tu canal de voz, silenciado y ensordecido")
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
        try:
            await self.join(interaction.guild, target)
        except Exception:
            log.exception("No se pudo conectar a la voz")
            return await interaction.followup.send(
                embed=error("No pude conectarme. Revisá mis permisos y probá de nuevo.")
            )
        await interaction.followup.send(embed=ok(f"Entré a {target.mention} silenciado y ensordecido."))

    @app_commands.command(name="salir", description="El bot sale del canal de voz")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def salir(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc is None:
            return await interaction.response.send_message(embed=error("No estoy en ningún canal de voz."), ephemeral=True)
        await vc.disconnect(force=True)
        await interaction.response.send_message(embed=ok("Salí del canal de voz."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice247(bot))
