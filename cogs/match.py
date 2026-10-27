import asyncio
import hashlib
import io
import random

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageChops, ImageDraw

from utils.fonts import fit_font, get_font

W, H = 900, 450


def compatibility(id_a: int, id_b: int) -> int:
    """Porcentaje fijo para cada pareja: siempre da lo mismo sin importar el orden."""
    if id_a == id_b:
        return 100
    lo, hi = sorted((id_a, id_b))
    digest = hashlib.sha256(f"{lo}:{hi}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 101


def phrase(pct: int, same: bool) -> str:
    if same:
        return "Amor propio: nivel máximo"
    if pct == 100:
        return "¡Destinados! Casense ya"
    if pct >= 90:
        return "¡Almas gemelas!"
    if pct >= 70:
        return "Hay mucha química, ¡tirenle para adelante!"
    if pct >= 50:
        return "Hay onda... pueden funcionar"
    if pct >= 30:
        return "Mmm, mejor como amigos"
    if pct >= 10:
        return "Poca química, che"
    return "Ni en otra vida"


def heart_image(size: int, color: tuple[int, int, int, int]) -> Image.Image:
    """Corazón suave (dibujado en grande y reducido para que no se vea pixelado)."""
    s = size * 4
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    r = 0.26 * s
    for cx in (0.30 * s, 0.70 * s):
        d.ellipse((cx - r, 0.32 * s - r, cx + r, 0.32 * s + r), fill=color)
    d.polygon([(0.06 * s, 0.42 * s), (0.94 * s, 0.42 * s), (0.50 * s, 0.93 * s)], fill=color)
    return layer.resize((size, size), Image.LANCZOS)


def filled_heart(size: int, pct: int) -> Image.Image:
    """Corazón que se llena de abajo hacia arriba según el porcentaje."""
    base = heart_image(size, (255, 255, 255, 55))
    if pct > 0:
        full = heart_image(size, (255, 64, 105, 255))
        top = 0.93 - 0.87 * pct / 100  # el corazón ocupa de 6% a 93% del alto
        cut = int(top * size)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rectangle((0, cut, size, size), fill=255)
        full.putalpha(ImageChops.multiply(full.getchannel("A"), mask))
        base.alpha_composite(full)
    return base


def circle_avatar(data: bytes | None, size: int, fallback_color: tuple[int, int, int]) -> Image.Image:
    if data:
        try:
            av = Image.open(io.BytesIO(data)).convert("RGB").resize((size, size), Image.LANCZOS)
        except Exception:
            av = Image.new("RGB", (size, size), fallback_color)
    else:
        av = Image.new("RGB", (size, size), fallback_color)
    big = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = big.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(av, (0, 0), mask)
    return out


def render_match(av1: bytes | None, av2: bytes | None, name1: str, name2: str, pct: int, same: bool) -> io.BytesIO:
    # Fondo con degradé violeta -> rosa
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    top, bottom = (46, 16, 101), (168, 28, 88)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    img = img.convert("RGBA")

    # Corazoncitos de fondo (posiciones fijas para cada pareja)
    rng = random.Random(pct * 7919 + len(name1) * 31 + len(name2))
    zones = [(20, 860, 8, 48), (275, 325, 90, 280), (575, 625, 90, 280), (20, 860, 405, 425)]
    for _ in range(18):
        x1, x2, y1, y2 = rng.choice(zones)
        size = rng.randint(14, 30)
        x = rng.randint(x1, max(x1, x2 - size))
        y = rng.randint(y1, max(y1, y2 - size // 2))
        alpha = rng.randint(70, 160)
        color = rng.choice([(255, 182, 193), (255, 255, 255), (255, 120, 160)])
        img.alpha_composite(heart_image(size, (*color, alpha)), (min(x, W - size), min(y, H - size)))

    # Avatares con aro
    av_size = 200
    centers = [(170, 185), (730, 185)]
    ring = ImageDraw.Draw(img)
    for (cx, cy), data, fb in zip(centers, (av1, av2), ((120, 90, 200), (200, 90, 140))):
        ring.ellipse((cx - av_size // 2 - 7, cy - av_size // 2 - 7, cx + av_size // 2 + 7, cy + av_size // 2 + 7), fill=(255, 255, 255, 235))
        img.alpha_composite(circle_avatar(data, av_size, fb), (cx - av_size // 2, cy - av_size // 2))

    # Corazón central
    heart_size = 230
    img.alpha_composite(filled_heart(heart_size, pct), (450 - heart_size // 2, 175 - heart_size // 2))

    draw = ImageDraw.Draw(img)
    draw.text((450, 162), f"{pct}%", font=get_font(58), fill="white", anchor="mm", stroke_width=4, stroke_fill=(90, 10, 45))

    # Nombres y frase (el tamaño se ajusta solo para que nunca se salgan de la imagen)
    for (cx, _), name in zip(centers, (name1, name2)):
        name = name[:30]
        draw.text((cx, 312), name, font=fit_font(draw, name, 290, 28, 16), fill="white", anchor="mm")
    text = phrase(pct, same)
    draw.text((450, 375), text, font=fit_font(draw, text, 820, 30, 18), fill=(255, 226, 236), anchor="mm")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf


async def _avatar_bytes(member: discord.abc.User) -> bytes | None:
    try:
        return await member.display_avatar.replace(size=256, format="png").read()
    except discord.HTTPException:
        return None


class Match(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="match", description="💘 Mirá qué tan compatibles son dos personas")
    @app_commands.describe(usuario1="Primera persona", usuario2="Segunda persona (si no elegís, sos vos)")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5.0)
    async def match(self, interaction: discord.Interaction, usuario1: discord.Member, usuario2: discord.Member | None = None):
        other = usuario2 or interaction.user
        await interaction.response.defer()

        av1, av2 = await asyncio.gather(_avatar_bytes(usuario1), _avatar_bytes(other))
        pct = compatibility(usuario1.id, other.id)
        buf = await asyncio.to_thread(
            render_match, av1, av2, usuario1.display_name, other.display_name, pct, usuario1.id == other.id
        )
        await interaction.followup.send(
            content=f"💘 {usuario1.mention} + {other.mention}",
            file=discord.File(buf, filename="match.png"),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Match(bot))
