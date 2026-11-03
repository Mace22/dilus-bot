"""Imágenes de los cofres para Discord: GIF de apertura (ruleta horizontal) y tarjeta de resultado. Solo Pillow."""
import io
import random

from PIL import Image, ImageDraw, ImageFilter

from utils import chest_config as cc
from utils.fonts import fit_font, get_font

W, H = 640, 190                   # tamaño del GIF
ITEM_W, ITEM_H, GAP = 100, 124, 8
STEP = ITEM_W + GAP

PALETTE = {                       # (cuerpo, oscuro, acento, brillo)
    "common": ((88, 96, 110), (44, 50, 62), (203, 213, 225), (156, 163, 175)),
    "rare": ((37, 99, 235), (21, 48, 118), (147, 197, 253), (59, 130, 246)),
    "epic": ((124, 58, 237), (64, 30, 128), (196, 181, 253), (139, 92, 246)),
    "legendary": ((212, 160, 23), (118, 78, 10), (253, 230, 138), (245, 179, 1)),
}


def _hex(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _bg(w: int, h: int, glow: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (w, h), (10, 10, 18, 255))
    d = ImageDraw.Draw(img)
    for y in range(h):                                                  # degradé vertical suave
        t = abs(y - h / 2) / (h / 2)
        k = 1 - t * 0.75
        d.line([(0, y), (w, y)], fill=(int(14 + glow[0] * 0.10 * k), int(14 + glow[1] * 0.10 * k), int(22 + glow[2] * 0.14 * k), 255))
    return img


def draw_chest(img: Image.Image, cx: float, base_y: float, w: float, rarity: str, opened: bool = False):
    """Dibuja un cofre estilizado con los colores de su rareza (cerrado o abierto, con luz)."""
    body, dark, accent, glow = PALETTE[rarity]
    d = ImageDraw.Draw(img, "RGBA")
    x0, x1 = cx - w / 2, cx + w / 2
    body_h = w * 0.52
    y_top = base_y - body_h
    r = w * 0.06
    # sombra
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((x0 - w * 0.05, base_y - w * 0.06, x1 + w * 0.05, base_y + w * 0.08), fill=(0, 0, 0, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(w * 0.04)))
    if opened:                                                          # luz que sale del cofre
        beam = Image.new("RGBA", img.size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(beam)
        for i, a in enumerate((70, 50, 34, 20)):
            spread = w * (0.20 + i * 0.16)
            bd.polygon([(cx - w * 0.36, y_top), (cx + w * 0.36, y_top), (cx + spread + w * 0.2, y_top - w * 1.2), (cx - spread - w * 0.2, y_top - w * 1.2)], fill=glow + (a,))
        img.alpha_composite(beam.filter(ImageFilter.GaussianBlur(w * 0.05)))
        d = ImageDraw.Draw(img, "RGBA")
    # cuerpo
    d.rounded_rectangle((x0, y_top, x1, base_y), radius=r, fill=dark + (255,), outline=accent + (255,), width=max(2, int(w * 0.018)))
    d.rounded_rectangle((x0 + w * 0.035, y_top + w * 0.035, x1 - w * 0.035, base_y - w * 0.035), radius=r * 0.7, fill=body + (255,))
    for bx in (x0 + w * 0.14, x1 - w * 0.14 - w * 0.09):                # bandas de metal
        d.rectangle((bx, y_top, bx + w * 0.09, base_y), fill=accent + (210,))
    d.rectangle((x0, y_top + w * 0.02, x1, y_top + w * 0.07), fill=dark + (255,))
    if opened:                                                          # interior brillante y tapa levantada
        d.rounded_rectangle((x0 + w * 0.05, y_top - w * 0.02, x1 - w * 0.05, y_top + w * 0.09), radius=r * 0.5, fill=tuple(min(255, c + 70) for c in glow) + (255,))
        lid = [(x0 + w * 0.02, y_top), (x1 - w * 0.02, y_top), (x1 - w * 0.10, y_top - w * 0.36), (x0 + w * 0.10, y_top - w * 0.36)]
        d.polygon(lid, fill=body + (255,), outline=accent + (255,))
        d.line([lid[3], lid[2]], fill=accent + (255,), width=max(2, int(w * 0.03)))
    else:
        d.rounded_rectangle((x0, y_top - w * 0.30, x1, y_top + w * 0.05), radius=w * 0.22, fill=dark + (255,), outline=accent + (255,), width=max(2, int(w * 0.018)), corners=(True, True, False, False))
        d.rounded_rectangle((x0 + w * 0.035, y_top - w * 0.265, x1 - w * 0.035, y_top + w * 0.02), radius=w * 0.19, fill=body + (255,), corners=(True, True, False, False))
        for bx in (x0 + w * 0.14, x1 - w * 0.14 - w * 0.09):
            d.rectangle((bx, y_top - w * 0.24, bx + w * 0.09, y_top + w * 0.03), fill=accent + (210,))
    lock_y = y_top + (w * 0.03 if not opened else w * 0.12)             # cerradura dorada
    d.rounded_rectangle((cx - w * 0.07, lock_y - w * 0.05, cx + w * 0.07, lock_y + w * 0.11), radius=w * 0.025, fill=(236, 200, 96, 255), outline=(150, 105, 20, 255), width=max(1, int(w * 0.012)))
    d.ellipse((cx - w * 0.02, lock_y, cx + w * 0.02, lock_y + w * 0.04), fill=(80, 55, 10, 255))


def _coin(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(232, 195, 90, 255), outline=(184, 144, 43, 255), width=max(1, int(r * 0.18)))
    d.text((cx, cy), "$", font=get_font(max(8, int(r * 1.3))), fill=(138, 100, 20, 255), anchor="mm")


def _item_card(amount: int, segment: int, size: tuple[int, int] = (ITEM_W, ITEM_H)) -> Image.Image:
    w, h = size
    color = _hex(cc.SEGMENT_COLORS[segment])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=12, fill=(24, 26, 38, 255), outline=color + (150,), width=2)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((w * 0.1, h * 0.08, w * 0.9, h * 0.62), fill=color + (70,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img, "RGBA")
    _coin(d, w / 2, h * 0.30, 15)
    text = f"{amount:,}".replace(",", ".")
    d.text((w / 2, h * 0.57), text, font=fit_font(d, text, w - 14, 26, 14), fill=(255, 255, 255, 255), anchor="mm")
    d.rounded_rectangle((8, h - 28, w - 9, h - 8), radius=8, fill=color + (255,))
    name = cc.SEGMENT_NAMES[segment].replace("¡", "").replace("!", "")
    d.text((w / 2, h - 18), name.upper(), font=fit_font(d, name.upper(), w - 24, 11, 8), fill=(10, 10, 18, 255), anchor="mm")
    return img


def build_reel(rarity: str, scale: float, reward: int, segment: int, rng: random.Random | None = None, n: int = 40, win_index: int = 31) -> list[tuple[int, int]]:
    """Lista de (monedas, tramo) para la ruleta. La posición `win_index` es SIEMPRE el premio real; el resto son de relleno."""
    rng = rng or random.Random()
    segs = cc.segments(rarity, scale)
    weights = [s["weight"] for s in segs]
    items = []
    for _ in range(n):
        s = rng.choices(segs, weights)[0]
        items.append((cc.r5(rng.randint(s["lo"], s["hi"])), s["index"]))
    items[win_index] = (reward, segment)
    return items


def render_open_gif(rarity: str, items: list[tuple[int, int]], win_index: int, rng: random.Random | None = None, frames: int = 44) -> io.BytesIO:
    """GIF de la ruleta: la tira se desliza y frena exactamente sobre el premio real (items[win_index])."""
    rng = rng or random.Random()
    glow = PALETTE[rarity][3]
    strip = Image.new("RGBA", (len(items) * STEP + W, H), (0, 0, 0, 0))
    for i, (amount, seg) in enumerate(items):
        strip.alpha_composite(_item_card(amount, seg), (i * STEP, (H - ITEM_H) // 2))
    jitter = rng.uniform(-0.3, 0.3) * ITEM_W                                  # frena en cualquier parte del casillero ganador
    end_x = win_index * STEP + ITEM_W / 2 + jitter - W / 2                    # desplazamiento final: el indicador central queda sobre el premio real
    bg = _bg(W, H, glow)
    fade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fade)
    for x in range(110):                                                      # bordes oscuros a los costados
        a = int(235 * (1 - x / 110) ** 2)
        fd.line([(x, 0), (x, H)], fill=(10, 10, 18, a)); fd.line([(W - 1 - x, 0), (W - 1 - x, H)], fill=(10, 10, 18, a))

    def frame(offset: float, final: bool) -> Image.Image:
        f = bg.copy()
        f.alpha_composite(strip.crop((int(offset), 0, int(offset) + W, H)))
        f.alpha_composite(fade)
        d = ImageDraw.Draw(f, "RGBA")
        if final:                                                              # marco sobre el premio ganador
            wx = win_index * STEP + ITEM_W / 2 - end_x
            d.rounded_rectangle((wx - ITEM_W / 2 - 4, (H - ITEM_H) // 2 - 4, wx + ITEM_W / 2 + 4, (H + ITEM_H) // 2 + 4), radius=14, outline=glow + (255,), width=4)
        d.line([(W // 2, 8), (W // 2, H - 8)], fill=(255, 224, 130, 255), width=3)             # indicador central
        d.polygon([(W // 2 - 10, 0), (W // 2 + 10, 0), (W // 2, 14)], fill=(255, 224, 130, 255))
        d.polygon([(W // 2 - 10, H), (W // 2 + 10, H), (W // 2, H - 14)], fill=(255, 224, 130, 255))
        return f

    out = []
    for i in range(frames):
        u = i / (frames - 1)
        p = 1 - (1 - u) ** 4                                                   # arranca rápido y frena de a poco
        out.append(frame(p * end_x, final=False))
    final = frame(end_x, final=True)
    out += [final, final]
    sample = Image.new("RGB", (W, H * 3))
    for k, im in enumerate((out[0], out[len(out) // 2], final)):
        sample.paste(im.convert("RGB"), (0, k * H))
    pal = sample.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pframes = [im.convert("RGB").quantize(palette=pal, dither=Image.Dither.NONE) for im in out]
    durations = [58] * (len(pframes) - 3) + [110, 180, 6000]
    buf = io.BytesIO()
    pframes[0].save(buf, format="GIF", save_all=True, append_images=pframes[1:], duration=durations, loop=0, optimize=False)
    buf.seek(0)
    return buf


def render_result_png(rarity: str, reward: int, segment: int, title: str = "", subtitle: str = "") -> io.BytesIO:
    """Tarjeta final: cofre abierto con luz, monedas ganadas y el tramo del premio."""
    w, h = 640, 260
    ss = 2
    glow = PALETTE[rarity][3]
    img = _bg(w * ss, h * ss, glow)
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((w * ss * 0.02, h * ss * 0.1, w * ss * 0.52, h * ss * 1.1), fill=glow + (80,))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(40 * ss)))
    draw_chest(img, w * ss * 0.26, h * ss * 0.86, w * ss * 0.30, rarity, opened=True)
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle((8 * ss, 8 * ss, (w - 8) * ss, (h - 8) * ss), radius=26 * ss, outline=glow + (200,), width=3 * ss)
    seg_color = _hex(cc.SEGMENT_COLORS[segment])
    x = w * ss * 0.56
    d.text((x, 52 * ss), (title or f"COFRE {cc.RARITY_NAME[rarity].upper()}"), font=get_font(20 * ss), fill=glow + (255,), anchor="lm")
    _coin(d, x + 24 * ss, 118 * ss, 24 * ss)
    amount = f"+{reward:,}".replace(",", ".")
    d.text((x + 58 * ss, 118 * ss), amount, font=fit_font(d, amount, 196 * ss, 54 * ss, 24 * ss), fill=(255, 241, 184, 255), anchor="lm")
    d.rounded_rectangle((x, 160 * ss, x + 170 * ss, 188 * ss), radius=14 * ss, fill=seg_color + (255,))
    seg_name = cc.SEGMENT_NAMES[segment].upper()
    d.text((x + 85 * ss, 174 * ss), seg_name, font=fit_font(d, seg_name, 150 * ss, 15 * ss, 9 * ss), fill=(10, 10, 18, 255), anchor="mm")
    if subtitle:
        d.text((x, 214 * ss), subtitle, font=fit_font(d, subtitle, w * ss * 0.40, 16 * ss, 9 * ss), fill=(200, 205, 220, 255), anchor="lm")
    img = img.resize((w, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf
