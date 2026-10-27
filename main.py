import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from utils.db import Database
from utils.embeds import BRAND_NAME, error

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("dilus-bot")

EXTENSIONS = [
    "cogs.levels",
    "cogs.voice247",
    "cogs.config",
    "cogs.moderation",
    "cogs.tickets",
    "cogs.giveaways",
    "cogs.utility",
]


class DilusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True           # bienvenida, autorole, niveles
        intents.message_content = True   # XP por mensajes
        intents.voice_states = True      # voz 24/7 y XP por voz

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            activity=discord.Activity(type=discord.ActivityType.watching, name=f"{BRAND_NAME} | /ayuda"),
        )
        self.db = Database("data/dilu.db")
        self.tree.on_error = self.on_tree_error

    async def setup_hook(self):
        await self.db.connect()
        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                log.info("Módulo cargado: %s", ext)
            except Exception:
                log.exception("No se pudo cargar %s", ext)
        synced = await self.tree.sync()
        log.info("Slash commands sincronizados: %d", len(synced))

    async def on_ready(self):
        log.info("Conectado como %s (id: %s) en %d servidor(es)", self.user, self.user.id, len(self.guilds))

    async def close(self):
        await self.db.close()
        await super().close()

    async def on_tree_error(self, interaction: discord.Interaction, err: app_commands.AppCommandError):
        if isinstance(err, app_commands.MissingPermissions):
            msg = "No tenés permisos para usar este comando."
        elif isinstance(err, app_commands.BotMissingPermissions):
            perms = ", ".join(err.missing_permissions)
            msg = f"Me faltan permisos para hacer eso: `{perms}`."
        elif isinstance(err, app_commands.CommandOnCooldown):
            msg = f"Esperá {err.retry_after:.0f}s antes de volver a usarlo."
        elif isinstance(err, app_commands.NoPrivateMessage):
            msg = "Este comando solo funciona dentro de un servidor."
        else:
            log.exception("Error en comando /%s", getattr(interaction.command, "name", "?"), exc_info=err)
            msg = "Ocurrió un error inesperado. Probá de nuevo en un rato."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=error(msg), ephemeral=True)
            else:
                await interaction.response.send_message(embed=error(msg), ephemeral=True)
        except discord.HTTPException:
            pass


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit(
            "Falta DISCORD_TOKEN. Creá un archivo .env (mirá .env.example) "
            "o cargalo como variable de entorno en el panel del hosting."
        )
    DilusBot().run(token, log_handler=None)


if __name__ == "__main__":
    main()
