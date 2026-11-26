"""Canal de features: los juegos que llenan el chat (blackjack, ruleta, slots...) solo se usan ahí.

- Si el servidor no configuró ningún canal de features, los juegos funcionan en todos los canales (como antes).
- Si el canal configurado fue borrado, también se considera "sin restricción" para no dejar los juegos trabados.
- Los hilos que cuelgan del canal de features también cuentan como canal de features.
"""
import discord
from discord import app_commands

from utils.embeds import error

FEATURES_KEY = "features_channel"
GAMES_TEXT = "Blackjack, ruleta, slots, apostar y duelos de cara o cruz"


class WrongChannel(app_commands.CheckFailure):
    """Se usó un juego fuera del canal de features."""

    def __init__(self, channel_id: int):
        super().__init__("Canal incorrecto")
        self.channel_id = channel_id


def wrong_channel_embed(channel_id: int) -> discord.Embed:
    return error(f"Este comando se puede usar solo en el canal de features: <#{channel_id}>")


async def redirect_for(bot, guild_id: int, channel_id: int | None, parent_id: int | None = None) -> int | None:
    """Devuelve None si se puede jugar en este canal, o el ID del canal de features al que hay que ir."""
    fid = await bot.db.get_setting(guild_id, FEATURES_KEY)
    if not fid:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None or guild.get_channel(fid) is None:
        return None
    if channel_id == fid or (parent_id is not None and parent_id == fid):
        return None
    return fid


def features_only():
    """Decorador para comandos de juego: solo se pueden usar en el canal de features (si hay uno configurado)."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None:
            return True
        parent_id = getattr(interaction.channel, "parent_id", None)
        fid = await redirect_for(interaction.client, interaction.guild_id, interaction.channel_id, parent_id)
        if fid:
            raise WrongChannel(fid)
        return True

    return app_commands.check(predicate)
