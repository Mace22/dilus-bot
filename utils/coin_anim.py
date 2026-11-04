"""Animación de la moneda para los duelos de Discord: un GIF de la moneda girando y una imagen final con el lado que salió."""
import io
import math
from functools import lru_cache

from PIL import Image, ImageDraw

from utils.fonts import get_font

BG = (43, 45, 49)                 # color de fondo de los embeds oscuros de Discord
GOLD, GOLD_LIGHT, GOLD_DARK, RIM = (232, 195, 90), (250, 226, 140), (176, 137, 38), (201, 162, 58)
INK = (122, 86, 14)

W, H = 240, 280                  # tamaño final de cada cuadro
SS = 2                            # supersampling (bordes más suaves)
R = 78                            # radio de la moneda (en tamaño final)
FRAMES = 26
HALF_TURNS = 8                    # medias vueltas (se ajusta para terminar en el lado correcto)


@lru_cache(maxsize=2)
def _disc(face: str) -> Image.Image:
    """La moneda de frente (cara o cruz), dibujada grande."""
    d = 2 * R * SS
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    g.ellipse([0, 0, d - 1, d - 1], fill=GOLD_DARK)
    g.ellipse([d * 0.03, d * 0.03, d * 0.97, d * 0.97], fill=RIM)
    g.ellipse([d * 0.07, d * 0.07, d * 0.93, d * 0.93], fill=GOLD)
    g.ellipse([d * 0.13, d * 0.13, d * 0.87, d * 0.87], outline=RIM, width=max(2, d // 60))
    g.pieslice([d * 0.16, d * 0.12, d * 0.62, d * 0.58], 180, 270, fill=GOLD_LIGHT)   # brillo
    cx, cy, u = d / 2, d / 2, d / 100
    if face == "cara":
        for ex in (-14, 14):
            g.ellipse([cx + (ex - 6) * u, cy - 22 * u, cx + (ex + 6) * u, cy - 6 * u], fill=INK)
        g.arc([cx - 24 * u, cy - 16 * u, cx + 24 * u, cy + 24 * u], 20, 160, fill=INK, width=int(6 * u))
        label = "CARA"
    else:
        w = int(10 * u)
        g.line([cx - 22 * u, cy - 26 * u, cx + 22 * u, cy + 18 * u], fill=INK, width=w)
        g.line([cx + 22 * u, cy - 26 * u, cx - 22 * u, cy + 18 * u], fill=INK, width=w)
        label = "CRUZ"
    font = get_font(int(11 * u))
    tw = g.textlength(label, font=font)
    g.text((cx - tw / 2, cy + 27 * u), label, font=font, fill=INK)
    return img


def _frame(face: str, c: float, lift: float) -> Image.Image:
    """Un cuadro: moneda con ancho |c| (giro en 3D) elevada `lift` píxeles."""
    canvas = Image.new("RGB", (W * SS, H * SS), BG)
    g = ImageDraw.Draw(canvas, "RGBA")
    cx, ground = W * SS // 2, int(H * 0.88 * SS)
    k = max(0.35, 1 - lift / 110)                                                  # la sombra se achica al subir
    sw, sh = int(R * 0.9 * k * SS), int(9 * k * SS)
    g.ellipse([cx - sw, ground - sh, cx + sw, ground + sh], fill=(0, 0, 0, 90))
    disc = _disc(face)
    width = max(3 * SS, int(disc.width * abs(c)))
    coin = disc.resize((width, disc.height), Image.LANCZOS)
    y = int(ground - 2 * R * SS - 10 * SS - lift * SS)
    if abs(c) < 0.18:                                                              # de canto: se ve el grosor
        edge = int(R * 0.28 * SS)
        g.rounded_rectangle([cx - edge // 7, y, cx + edge // 7, y + disc.height], radius=edge // 7, fill=GOLD_DARK)
    else:
        canvas.paste(coin, (cx - width // 2, y), coin)
    return canvas.resize((W, H), Image.LANCZOS)


def render(result: str) -> tuple[bytes, bytes]:
    """(gif, png): la moneda girando y cayendo del lado `result` ('cara' o 'cruz'), y la imagen final quieta."""
    turns = HALF_TURNS + (0 if result == "cara" else 1)         # par = cara, impar = cruz
    frames, durations = [], []
    for i in range(FRAMES):
        t = i / (FRAMES - 1)
        eased = 1 - (1 - t) ** 3
        phi = turns * math.pi * eased
        c = math.cos(phi)
        face = "cara" if c >= 0 else "cruz"
        lift = math.sin(math.pi * t) * 62
        frames.append(_frame(face, c, lift))
        durations.append(45 + int(90 * t ** 2))
    final = _frame(result, 1.0, 0)
    frames.append(final); durations.append(2500)                  # se queda mostrando el resultado

    pal = frames[0].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    quant = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    gif = io.BytesIO()
    quant[0].save(gif, format="GIF", save_all=True, append_images=quant[1:], duration=durations, loop=0, disposal=1)
    png = io.BytesIO()
    final.save(png, format="PNG")
    return gif.getvalue(), png.getvalue()
