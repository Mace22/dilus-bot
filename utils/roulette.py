"""LÃ³gica y grÃ¡ficos de la ruleta europea (37 casilleros: 0 a 36).

Este archivo no usa nada de Discord: solo reglas, pagos y dibujo de imÃ¡genes con Pillow.
El comando y los botones estÃ¡n en cogs/roulette.py.
"""
import io
import math
import random
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from utils.fonts import fit_font, get_font

# ----------------------------------------------------------------------
# Reglas
# ----------------------------------------------------------------------
# Orden real de los casilleros en la rueda europea
WHEEL_ORDER = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24,
    16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
]
STEP = 360 / 37
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

COLOR_NAME = {"red": "Rojo", "black": "Negro", "green": "Verde"}
COLOR_EMOJI = {"red": "ðŸ”´", "black": "âš«", "green": "ðŸŸ¢"}


def color_of(n: int) -> str:
    if n == 0:
        return "green"
    return "red" if n in RED_NUMBERS else "black"


@dataclass(frozen=True)
class BetType:
    key: str
    label: str      # nombre corto
    emoji: str
    mult: int       # monedas que se devuelven por cada moneda apostada (ganancia + apuesta)
    count: int      # cuÃ¡ntos nÃºmeros (de 37) cubre
    hint: str       # explicaciÃ³n cortita

    @property
    def ratio(self) -> int:
        """Ganancia por moneda apostada (el famoso "paga 35 a 1")."""
        return self.mult - 1

    @property
    def prob(self) -> float:
        return self.count / 37


BET_TYPES: dict[str, BetType] = {
    b.key: b
    for b in [
        BetType("red", "Rojo", "ðŸ”´", 2, 18, "Salen los 18 nÃºmeros rojos"),
        BetType("black", "Negro", "âš«", 2, 18, "Salen los 18 nÃºmeros negros"),
        BetType("even", "Par", "2ï¸âƒ£", 2, 18, "NÃºmeros pares (el 0 no cuenta)"),
        BetType("odd", "Impar", "1ï¸âƒ£", 2, 18, "NÃºmeros impares"),
        BetType("low", "1-18 (baja)", "â¬‡ï¸", 2, 18, "Del 1 al 18"),
        BetType("high", "19-36 (alta)", "â¬†ï¸", 2, 18, "Del 19 al 36"),
        BetType("doc1", "1Âª docena (1-12)", "ðŸ¥‡", 3, 12, "Del 1 al 12"),
        BetType("doc2", "2Âª docena (13-24)", "ðŸ¥ˆ", 3, 12, "Del 13 al 24"),
        BetType("doc3", "3Âª docena (25-36)", "ðŸ¥‰", 3, 12, "Del 25 al 36"),
        BetType("col1", "Columna 1", "1ï¸âƒ£", 3, 12, "1, 4, 7 â€¦ 34"),
        BetType("col2", "Columna 2", "2ï¸âƒ£", 3, 12, "2, 5, 8 â€¦ 35"),
        BetType("col3", "Columna 3", "3ï¸âƒ£", 3, 12, "3, 6, 9 â€¦ 36"),
    ]
}
STRAIGHT = BetType("straight", "NÃºmero pleno", "ðŸŽ¯", 36, 1, "ElegÃ­s un nÃºmero del 0 al 36")
OUTSIDE = ["low", "even", "red", "black", "odd", "high"]   # orden en el tablero


def bet_info(key: str) -> BetType:
    """Datos de una apuesta. Los nÃºmeros se guardan como 'n17'."""
    if key.startswith("n"):
        n = int(key[1:])
        return BetType(key, f"NÃºmero {n}", COLOR_EMOJI[color_of(n)], 36, 1, f"Solo gana si sale el {n}")
    return BET_TYPES[key]


_RULES = {
    "red": lambda n: n in RED_NUMBERS,
    "black": lambda n: n not in RED_NUMBERS,
    "even": lambda n: n % 2 == 0,
    "odd": lambda n: n % 2 == 1,
    "low": lambda n: n <= 18,
    "high": lambda n: n >= 19,
    "doc1": lambda n: n <= 12,
    "doc2": lambda n: 13 <= n <= 24,
    "doc3": lambda n: n >= 25,
    "col1": lambda n: n % 3 == 1,
    "col2": lambda n: n % 3 == 2,
    "col3": lambda n: n % 3 == 0,
}


def wins(key: str, number: int) -> bool:
    if key.startswith("n"):
        return number == int(key[1:])
    if number == 0:           # el cero es verde: todas las apuestas "externas" pierden
        return False
    return _RULES[key](number)


def payout(key: str, amount: int, number: int) -> int:
    """Total que se le devuelve a la persona por esta apuesta (0 si perdiÃ³)."""
    return amount * bet_info(key).mult if wins(key, number) else 0


def number_tags(n: int) -> list[str]:
    """DescripciÃ³n de un nÃºmero: ['Negro', 'Impar', 'Baja (1-18)', '2Âª docena', 'Columna 2']."""
    if n == 0:
        return ["Cero (verde)"]
    return [
        COLOR_NAME[color_of(n)],
        "Par" if n % 2 == 0 else "Impar",
        "Baja (1-18)" if n <= 18 else "Alta (19-36)",
        f"{1 if n <= 12 else 2 if n <= 24 else 3}Âª docena",
        f"Columna {(n - 1) % 3 + 1}",
    ]


def spin() -> int:
    """NÃºmero ganador (usa el generador seguro del sistema operativo)."""
    return random.SystemRandom().randrange(37)


def pct(count: int) -> str:
    return f"{count / 37 * 100:.1f}".replace(".", ",") + "%"


def short(n: int) -> str:
    """Monto abreviado para las fichas: 950, 1,2k, 15k, 1,5M."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        v = n / 1000
        return (f"{v:.1f}".rstrip("0").rstrip(".") if v < 10 else f"{int(v)}").replace(".", ",") + "k"
    v = n / 1_000_000
    return f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "M"


def zone_keys() -> list[str]:
    return [f"n{i}" for i in range(37)] + list(BET_TYPES)


# ----------------------------------------------------------------------
# Tablero (imagen)
# ----------------------------------------------------------------------
W, H = 900, 460
CELL, CELL_H = 59, 58
MX, Y0 = 37, 92
DOZ_H, OUT_H = 50, 52

GOLD = (212, 175, 55)
GOLD_LIGHT = (244, 228, 160)
RED_C = (186, 28, 44)
BLACK_C = (22, 22, 30)
GREEN_C = (16, 120, 74)
LINE = (236, 236, 236)
PURPLE = (124, 58, 237)
COLOR_RGB = {"red": RED_C, "black": BLACK_C, "green": GREEN_C}


def _felt(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    center, edge = (24, 124, 80), (8, 56, 36)
    for y in range(h):
        t = min(1.0, abs(y - h / 2) / (h / 2)) ** 1.6
        d.line([(0, y), (w, y)], fill=tuple(int(center[i] + (edge[i] - center[i]) * t) for i in range(3)))
    return img.convert("RGBA")


def zone_rect(key: str) -> tuple[int, int, int, int]:
    """RectÃ¡ngulo (x0, y0, x1, y1) de cada zona apostable del tablero."""
    if key.startswith("n"):
        n = int(key[1:])
        if n == 0:
            return MX, Y0, MX + CELL, Y0 + 3 * CELL_H
        c, r = (n - 1) // 3, 2 - (n - 1) % 3          # fila de arriba: 3, 6, 9 â€¦ 36
        x, y = MX + CELL * (1 + c), Y0 + r * CELL_H
        return x, y, x + CELL, y + CELL_H
    if key.startswith("col"):
        r = 3 - int(key[3])                            # columna 3 = fila de arriba
        x, y = MX + CELL * 13, Y0 + r * CELL_H
        return x, y, x + CELL, y + CELL_H
    if key.startswith("doc"):
        k = int(key[3]) - 1
        x, y = MX + CELL * (1 + 4 * k), Y0 + 3 * CELL_H
        return x, y, x + 4 * CELL, y + DOZ_H
    i = OUTSIDE.index(key)
    x, y = MX + CELL * (1 + 2 * i), Y0 + 3 * CELL_H + DOZ_H
    return x, y, x + 2 * CELL, y + OUT_H


def _center(rect) -> tuple[int, int]:
    return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2


def _draw_chip(img: Image.Image, cx: int, cy: int, amount: int, r: int = 19):
    shadow = Image.new("RGBA", (r * 2 + 20, r * 2 + 20), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((10 + 2, 10 + 4, 10 + r * 2 + 2, 10 + r * 2 + 4), fill=(0, 0, 0, 150))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3)), (cx - r - 10, cy - r - 10))
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=PURPLE + (255,), outline=(255, 255, 255, 255), width=3)
    d.ellipse((cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5), outline=(255, 255, 255, 170), width=1)
    text = short(amount)
    d.text((cx, cy), text, font=fit_font(d, text, 2 * r - 12, 17 if r >= 19 else 15, 9), fill="white", anchor="mm")


def render_board(chips: dict[str, int], history: list[int], number: int | None = None, status: str | None = None) -> io.BytesIO:
    """Dibuja el paÃ±o de la ruleta.

    chips:   {zona: monedas apostadas en total}  (se dibujan como fichas)
    history: Ãºltimos nÃºmeros que salieron (el Ãºltimo es el mÃ¡s reciente)
    number:  si ya saliÃ³ un nÃºmero, se marcan las zonas ganadoras
    status:  texto de la etiqueta del centro cuando todavÃ­a no saliÃ³ nada
    """
    img = _felt(W, H)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 10, W - 10, H - 10), radius=28, outline=GOLD + (255,), width=4)
    d.rounded_rectangle((20, 20, W - 20, H - 20), radius=22, outline=GOLD + (110,), width=1)

    # ---- encabezado ----
    d.text((MX, 49), "RULETA EUROPEA", font=get_font(27), fill=GOLD_LIGHT + (255,), anchor="lm")

    pill_text, pill_color = None, None
    if number is not None:
        pill_text, pill_color = f"{number}  Â·  {COLOR_NAME[color_of(number)].upper()}", COLOR_RGB[color_of(number)]
    elif status:
        pill_text, pill_color = status, (34, 150, 80)
    if pill_text:
        f = fit_font(d, pill_text, 230, 22, 14)
        tw = int(d.textlength(pill_text, font=f))
        px = 442
        d.rounded_rectangle((px - tw // 2 - 22, 33, px + tw // 2 + 22, 65), radius=16, fill=pill_color + (255,), outline=(255, 255, 255, 235), width=3)
        d.text((px, 50), pill_text, font=f, fill="white", anchor="mm")

    recent = history[-8:]
    if recent:
        x0 = W - MX - (len(recent) * 36 - 6)
        d.text((x0, 27), "ÃšLTIMOS", font=get_font(13), fill=GOLD_LIGHT + (200,), anchor="lm")
        for i, n in enumerate(recent):
            cx, cy = x0 + i * 36 + 15, 53
            d.ellipse((cx - 15, cy - 15, cx + 15, cy + 15), fill=COLOR_RGB[color_of(n)] + (255,), outline=(255, 255, 255, 220), width=2)
            if i == len(recent) - 1:
                d.ellipse((cx - 18, cy - 18, cx + 18, cy + 18), outline=GOLD + (255,), width=3)
            d.text((cx, cy), str(n), font=get_font(15), fill="white", anchor="mm")

    # ---- tablero ----
    f_num = get_font(24)
    for n in range(37):
        rect = zone_rect(f"n{n}")
        d.rectangle(rect, fill=COLOR_RGB[color_of(n)] + (255,), outline=LINE + (255,), width=2)
        d.text(_center(rect), str(n), font=f_num, fill="white", anchor="mm")

    for k in (1, 2, 3):
        rect = zone_rect(f"col{k}")
        d.rectangle(rect, outline=LINE + (255,), width=2)
        d.text(_center(rect), "2:1", font=get_font(20), fill=GOLD_LIGHT + (255,), anchor="mm")

    for k, label in zip((1, 2, 3), ("1Âª DOCENA", "2Âª DOCENA", "3Âª DOCENA")):
        rect = zone_rect(f"doc{k}")
        d.rectangle(rect, outline=LINE + (255,), width=2)
        d.text((_center(rect)[0] - (22 if f"doc{k}" in chips else 0), _center(rect)[1]), label, font=get_font(21), fill="white", anchor="mm")

    labels = {"low": "1-18", "even": "PAR", "odd": "IMPAR", "high": "19-36"}
    for key in OUTSIDE:
        rect = zone_rect(key)
        d.rectangle(rect, outline=LINE + (255,), width=2)
        cx, cy = _center(rect)
        if key in chips:
            cx -= 20
        if key in labels:
            d.text((cx, cy), labels[key], font=get_font(21), fill="white", anchor="mm")
        else:  # rombo de color
            col = RED_C if key == "red" else BLACK_C
            d.polygon([(cx, cy - 19), (cx + 38, cy), (cx, cy + 19), (cx - 38, cy)], fill=col + (255,), outline=(255, 255, 255, 255))

    # ---- zonas ganadoras (resto opaco) ----
    if number is not None:
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        winners = [k for k in zone_keys() if wins(k, number)]
        for key in zone_keys():
            if key not in winners:
                od.rectangle(zone_rect(key), fill=(0, 0, 0, 125))
        for key in winners:
            x0, y0, x1, y1 = zone_rect(key)
            od.rectangle((x0, y0, x1, y1), fill=GOLD + (45,))
            od.rectangle((x0 + 1, y0 + 1, x1 - 1, y1 - 1), outline=GOLD + (255,), width=4)
        img.alpha_composite(overlay)

    # ---- fichas ----
    for key, amount in chips.items():
        if amount <= 0:
            continue
        rect = zone_rect(key)
        if key.startswith("doc"):
            _draw_chip(img, rect[2] - 30, _center(rect)[1], amount, 17)
        elif key in OUTSIDE:
            _draw_chip(img, rect[2] - 22, _center(rect)[1], amount, 17)
        else:
            _draw_chip(img, *_center(rect), amount)

    # ---- pie ----
    d = ImageDraw.Draw(img)
    d.text((W // 2, 392), "PAGOS   Â·   NÃºmero 35:1   Â·   Docena / Columna 2:1   Â·   Color, Par/Impar, 1-18 / 19-36  1:1",
           font=get_font(16), fill=GOLD_LIGHT + (255,), anchor="mm")
    d.text((W // 2, 420), "El 0 es verde: solo gana quien apostÃ³ al 0. Las demÃ¡s apuestas pierden.",
           font=get_font(15), fill=(200, 220, 205, 255), anchor="mm")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf


# ----------------------------------------------------------------------
# Rueda girando (GIF animado)
# ----------------------------------------------------------------------
GIF_SIZE = 400      # lienzo
WHEEL_SIZE = 360    # rueda dentro del lienzo


@lru_cache(maxsize=2)
def _wheel_base(size: int) -> Image.Image:
    """Rueda dibujada una sola vez (con suavizado); despuÃ©s solo se rota."""
    ss = 2
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2
    big = c - 2

    def circle(r, **kw):
        d.ellipse((c - r, c - r, c + r, c + r), **kw)

    circle(big, fill=(62, 36, 22, 255))
    circle(big * 0.965, fill=(88, 52, 30, 255))
    circle(big * 0.945, outline=GOLD + (255,), width=2 * ss)
    circle(big * 0.92, fill=(24, 26, 32, 255))                 # pista de la bola
    circle(big * 0.88, outline=(70, 74, 88, 255), width=ss)
    circle(big * 0.80, fill=(170, 150, 90, 255))               # borde de los casilleros

    r_out, r_in = big * 0.79, big * 0.56
    for i, n in enumerate(WHEEL_ORDER):
        start = i * STEP - 90 - STEP / 2
        d.pieslice((c - r_out, c - r_out, c + r_out, c + r_out), start, start + STEP, fill=COLOR_RGB[color_of(n)] + (255,))
    for i in range(37):
        a = math.radians(i * STEP - 90 - STEP / 2)
        d.line([(c + r_in * math.cos(a), c + r_in * math.sin(a)), (c + r_out * math.cos(a), c + r_out * math.sin(a))],
               fill=(205, 190, 140, 255), width=ss)

    circle(r_in, fill=(200, 165, 70, 255))                      # aro dorado interno
    circle(r_in * 0.95, fill=(40, 28, 20, 255))
    circle(r_in * 0.55, fill=(74, 46, 28, 255), outline=GOLD + (255,), width=2 * ss)
    for ang in (0, 90, 180, 270):                               # rayos
        a = math.radians(ang)
        d.line([(c, c), (c + r_in * 0.55 * math.cos(a), c + r_in * 0.55 * math.sin(a))], fill=GOLD + (255,), width=5 * ss)
    circle(r_in * 0.14, fill=GOLD_LIGHT + (255,), outline=GOLD + (255,), width=ss)

    # nÃºmeros: el texto se lee a lo largo del radio
    font = get_font(int(big * 0.105))
    r_text = big * 0.675
    for i, n in enumerate(WHEEL_ORDER):
        a = 90 - i * STEP                                       # Ã¡ngulo matemÃ¡tico (antihorario)
        tile = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((60, 30), str(n), font=font, fill=(255, 255, 255, 255), anchor="mm")
        tile = tile.rotate(a, expand=True, resample=Image.BICUBIC)
        x = c + r_text * math.cos(math.radians(a))
        y = c - r_text * math.sin(math.radians(a))
        img.alpha_composite(tile, (int(x - tile.width / 2), int(y - tile.height / 2)))

    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=1)
def _ball_sprite() -> Image.Image:
    """Bola con sombra. El centro de la bola estÃ¡ en (13, 12)."""
    k = 4
    w = 30 * k
    shadow = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((9 * k + 8, 8 * k + 12, 9 * k + 8 + 8 * k + 4, 8 * k + 12 + 8 * k + 4), fill=(0, 0, 0, 140))
    shadow = shadow.filter(ImageFilter.GaussianBlur(5))
    d = ImageDraw.Draw(shadow)
    cx, cy, r = 13 * k, 12 * k, 7 * k
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(238, 238, 240, 255), outline=(150, 150, 158, 255), width=k)
    d.ellipse((cx - r + 3 * k, cy - r + 2 * k, cx - 1, cy - 2), fill=(255, 255, 255, 255))
    return shadow.resize((30, 30), Image.LANCZOS)


@lru_cache(maxsize=1)
def _spin_background() -> Image.Image:
    bg = _felt(GIF_SIZE, GIF_SIZE)
    shadow = Image.new("RGBA", (GIF_SIZE, GIF_SIZE), (0, 0, 0, 0))
    m = (GIF_SIZE - WHEEL_SIZE) // 2
    ImageDraw.Draw(shadow).ellipse((m, m + 10, GIF_SIZE - m, GIF_SIZE - m + 10), fill=(0, 0, 0, 170))
    bg.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((4, 4, GIF_SIZE - 5, GIF_SIZE - 5), radius=26, outline=GOLD + (255,), width=3)
    return bg


def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def render_spin_gif(number: int, frames: int = 46) -> io.BytesIO:
    """GIF de la rueda girando. La bola termina clavada en el casillero de `number`."""
    base = _wheel_base(WHEEL_SIZE)
    bg = _spin_background()
    ball = _ball_sprite()
    cx = cy = GIF_SIZE / 2
    half = WHEEL_SIZE / 2
    off = (GIF_SIZE - WHEEL_SIZE) // 2

    idx = WHEEL_ORDER.index(number)
    pocket = 90 - idx * STEP            # Ã¡ngulo del casillero dentro de la rueda
    wheel_start = random.uniform(0, 360)
    laps_wheel, laps_ball = 0.6, 3.6    # la rueda gira hacia un lado y la bola hacia el otro
    r_track, r_pocket = half * 0.855, half * 0.675

    out: list[Image.Image] = []
    for i in range(frames):
        u = i / (frames - 1)
        p = 1 - (1 - u) ** 3                                    # frena de a poco
        theta_w = wheel_start + 360 * laps_wheel * p
        phi = pocket + 360 * laps_ball * (1 - p)
        theta_b = theta_w + phi

        s = _smooth((u - 0.60) / 0.34)                          # la bola baja hacia los casilleros
        r = r_track + (r_pocket - r_track) * s
        if 0.60 < u < 0.97:
            r += abs(math.sin((u - 0.60) * 26)) * (1 - s) ** 2 * half * 0.07   # rebotes

        frame = bg.copy()
        frame.alpha_composite(base.rotate(theta_w, resample=Image.BICUBIC), (off, off))
        bx = cx + r * math.cos(math.radians(theta_b))
        by = cy - r * math.sin(math.radians(theta_b))
        frame.alpha_composite(ball, (int(round(bx - 13)), int(round(by - 12))))
        out.append(frame)

    # Ãºltimo cuadro: cartel con el nÃºmero ganador en el centro de la rueda
    final = out[-1].copy()
    fd = ImageDraw.Draw(final)
    rb = half * 0.27
    fd.ellipse((cx - rb, cy - rb, cx + rb, cy + rb), fill=COLOR_RGB[color_of(number)] + (255,), outline=GOLD + (255,), width=4)
    fd.text((cx, cy + 1), str(number), font=get_font(46), fill="white", anchor="mm")
    out += [final, final]

    # una sola paleta para todos los cuadros (evita parpadeos de color)
    sample = Image.new("RGB", (GIF_SIZE, GIF_SIZE * 3))
    for k, f in enumerate((out[0], out[len(out) // 2], final)):
        sample.paste(f.convert("RGB"), (0, k * GIF_SIZE))
    pal = sample.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pframes = [f.convert("RGB").quantize(palette=pal, dither=Image.Dither.NONE) for f in out]

    durations = [85] * (len(pframes) - 2) + [400, 6000]
    buf = io.BytesIO()
    pframes[0].save(buf, format="GIF", save_all=True, append_images=pframes[1:], duration=durations, loop=0, optimize=False)
    buf.seek(0)
    return buf
