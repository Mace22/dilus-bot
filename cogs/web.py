import hashlib
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.embeds import error, make_embed

log = logging.getLogger("dilus-bot.web")

# ---------------------------------------------------------------------------
# Panel web. Variables de entorno (se cargan en el hosting, igual que el token):
#   DISCORD_CLIENT_SECRET -> "Client Secret" de tu app (Developer Portal > OAuth2). Sin esto el panel no se activa.
#   WEB_BASE_URL          -> dirección pública del panel, ej: https://panel.midominio.com  o  http://123.45.67.89:25565
#   WEB_PORT              -> puerto donde escucha (si no, usa SERVER_PORT / PORT / 8080)
#   SESSION_SECRET        -> (opcional) clave para firmar las sesiones; si falta se deriva del token del bot
# ---------------------------------------------------------------------------


class Web(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.server = None
        self.services = None
        self.url: str | None = None

    async def cog_load(self):
        client_secret = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
        if not client_secret:
            log.warning("Panel web desactivado: falta la variable DISCORD_CLIENT_SECRET.")
            return
        try:
            from web.server import WebServer
            from web.services import Services

            port = int(os.getenv("WEB_PORT") or os.getenv("SERVER_PORT") or os.getenv("PORT") or 8080)
            base_url = (os.getenv("WEB_BASE_URL") or f"http://localhost:{port}").strip()
            if not os.getenv("WEB_BASE_URL"):
                log.warning("Falta WEB_BASE_URL: el login con Discord solo va a funcionar en %s", base_url)
            token = getattr(self.bot.http, "token", None) or os.getenv("DISCORD_TOKEN", "")
            session_secret = (os.getenv("SESSION_SECRET") or hashlib.sha256(f"dilus-web|{token}".encode()).hexdigest()).encode()

            self.services = Services(self.bot)
            await self.services.recover()
            self.server = WebServer(
                self.bot, self.services, base_url=base_url, host=os.getenv("WEB_HOST", "0.0.0.0"), port=port,
                client_secret=client_secret, session_secret=session_secret,
            )
            await self.server.start()
            self.url = base_url.rstrip("/")
            self.sweeper.start()
            log.info("Redirect URI para el Developer Portal: %s/auth/callback", self.url)
        except Exception:
            log.exception("No pude iniciar el panel web (el resto del bot sigue funcionando).")
            self.server = None

    async def cog_unload(self):
        self.sweeper.cancel()
        if self.server:
            await self.server.stop()

    @tasks.loop(seconds=30)
    async def sweeper(self):
        """Cierra las manos de blackjack abandonadas en el panel."""
        if self.services:
            await self.services.sweep()

    @app_commands.command(name="panel", description="🌐 Abrí el panel web: tu economía, estadísticas, ruleta y blackjack")
    async def panel(self, interaction: discord.Interaction):
        if not self.url:
            return await interaction.response.send_message(embed=error("El panel web no está activado en este bot."), ephemeral=True)
        embed = make_embed(
            "🌐 Panel web de Dilu's Bot",
            "Entrá con tu cuenta de Discord y desde ahí podés:\n"
            "• 🪙 Ver tu saldo y reclamar **/daily** y **/trabajar**\n"
            "• 📊 Mirar tu nivel, XP, horas en voz y puestos\n"
            "• 🎡 Jugar a la **ruleta** y 🃏 al **blackjack**\n"
            "• 🛒 Comprar roles de la tienda y ver los rankings",
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Abrir panel", emoji="🌐", url=self.url))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Web(bot))
