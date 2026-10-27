import discord

BRAND_NAME = "Dilu's Bot"
BRAND_COLOR = 0x8B5CF6  # violeta
OK_COLOR = 0x22C55E
ERR_COLOR = 0xEF4444


def make_embed(title: str | None = None, description: str | None = None, *, color: int = BRAND_COLOR) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=BRAND_NAME)
    return embed


def ok(description: str) -> discord.Embed:
    return make_embed(description=f"✅ {description}", color=OK_COLOR)


def error(description: str) -> discord.Embed:
    return make_embed(description=f"❌ {description}", color=ERR_COLOR)
