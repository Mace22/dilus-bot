"""Imágenes del sistema de trabajo: tarjeta de nivel y ranking."""
import io

from PIL import Image, ImageDraw

from utils.fonts import fit_font, get_font
from utils import work as W

PALETTE = [(150, 150, 165), (96, 165, 250), (52, 211, 153), (167, 139, 250), (244, 114, 182),
           (251, 146, 60), (248, 113, 113), (250, 204, 21), (34, 211, 238), (255, 215, 0)]
MEDAL = [(255, 200, 40), (200, 205, 215), (205, 127, 50)]


def _clean(t: str) -> str:
    return "".join(c for c in t if ord(c) <= 0xFFFF) or "?"


def _bg(w, h, accent):
    img = Image.new("RGBA", (w, h), (13, 13, 22, 255))
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / h
        d.line((0, y, w, y), fill=(int(13 + 14 * k), int(13 + 10 * k), int(22 + 22 * k), 255))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((w - 330, -170, w + 100, 230), fill=(*accent, 55))
    img.alpha_composite(glow)
    return img


def _avatar(img, data, x, y, size, ring):
    d = ImageDraw.Draw(img)
    d.ellipse((x - 4, y - 4, x + size + 4, y + size + 4), fill=ring)
    if data:
        try:
            av = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size))
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
            img.paste(av, (x, y), mask)
            return
        except Exception:
            pass
    d.ellipse((x, y, x + size, y + size), fill=(40, 40, 60))


def _bar(d, x, y, w, h, frac, color):
    d.rounded_rectangle((x, y, x + w, y + h), h // 2, fill=(35, 35, 52))
    if frac > 0:
        d.rounded_rectangle((x, y, x + max(h, int(w * frac)), y + h), h // 2, fill=color)


def _out(img) -> io.BytesIO:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    buf.seek(0)
    return buf


def level_card(name: str, avatar: bytes | None, s: dict, coin: str = "") -> io.BytesIO:
    lvl = s["level"]
    col = PALETTE[min(lvl - 1, len(PALETTE) - 1)]
    w, h = 820, 300
    img = _bg(w, h, col)
    d = ImageDraw.Draw(img)
    _avatar(img, avatar, 36, 36, 120, col)
    d.text((184, 34), _clean(name), font=fit_font(d, _clean(name), 400, 36), fill=(255, 255, 255))
    d.rounded_rectangle((184, 86, 184 + 40 + len(s["title"]) * 16, 122), 18, fill=(*col, 255))
    d.text((204, 91), s["title"], font=get_font(22), fill=(15, 15, 25))
    d.text((w - 40, 30), "NIVEL", font=get_font(20), fill=(150, 150, 170), anchor="ra")
    d.text((w - 40, 50), str(lvl), font=get_font(84), fill=col, anchor="ra")
    need = s["xp_need"]
    frac = 1 if need is None else s["xp_in"] / need
    _bar(d, 36, 178, w - 72, 26, frac, col)
    label = "NIVEL MÁXIMO 👑".replace(" 👑", "") if need is None else f"{s['xp_in']} / {need} XP  →  {s['next_title']}"
    d.text((36, 148), label, font=get_font(20), fill=(210, 210, 225))
    d.text((w - 36, 148), f"Bono +{s['bonus']}%", font=get_font(20), fill=(52, 211, 153), anchor="ra")
    stats = [("Trabajos", s["works"]), ("Tareas", s["tasks"]), ("Racha", s["streak"]),
             ("Ganado", W_fmt(s["earned"])), ("Puesto", f"#{s['rank']}" if s["rank"] else "—")]
    cw = (w - 72) / len(stats)
    for i, (k, v) in enumerate(stats):
        x = 36 + i * cw
        d.rounded_rectangle((x, 226, x + cw - 10, 282), 12, fill=(24, 24, 38))
        d.text((x + 14, 232), k.upper(), font=get_font(13), fill=(140, 140, 160))
        d.text((x + 14, 250), str(v), font=fit_font(d, str(v), cw - 40, 24, 14), fill=(255, 255, 255))
    return _out(img)


def W_fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def ranking_card(title: str, rows: list[dict], me: dict | None = None) -> io.BytesIO:
    """rows: {name, avatar(bytes|None), xp, value(str), sub(str)}"""
    rh, top = 74, 96
    h = top + rh * max(len(rows), 1) + (70 if me else 24)
    w = 820
    img = _bg(w, h, (250, 204, 21))
    d = ImageDraw.Draw(img)
    d.text((36, 28), title, font=get_font(36), fill=(255, 255, 255))
    for i, r in enumerate(rows):
        y = top + i * rh
        lvl = W.level_of(r["xp"])
        col = PALETTE[min(lvl - 1, len(PALETTE) - 1)]
        d.rounded_rectangle((28, y, w - 28, y + rh - 8), 16, fill=(26, 26, 42) if i % 2 == 0 else (22, 22, 36))
        if i < 3:
            d.rounded_rectangle((28, y, 36, y + rh - 8), 4, fill=MEDAL[i])
        d.text((72, y + 33), str(i + 1), font=get_font(30), fill=MEDAL[i] if i < 3 else (150, 150, 170), anchor="mm")
        _avatar(img, r.get("avatar"), 104, y + 7, 52, col)
        nm = _clean(r["name"])
        d.text((176, y + 8), nm, font=fit_font(d, nm, 330, 24, 14), fill=(255, 255, 255))
        d.text((176, y + 38), r["sub"], font=get_font(15), fill=(150, 150, 170))
        d.rounded_rectangle((522, y + 18, 522 + 136, y + 48), 15, fill=(*col, 255))
        d.text((590, y + 33), f"Nv {lvl} {W.title_of(lvl)}", font=fit_font(d, f"Nv {lvl} {W.title_of(lvl)}", 124, 15, 10), fill=(15, 15, 25), anchor="mm")
        d.text((w - 44, y + 33), r["value"], font=get_font(24), fill=(255, 215, 0), anchor="rm")
    if not rows:
        d.text((w // 2, top + 30), "Todavía nadie trabajó", font=get_font(24), fill=(150, 150, 170), anchor="mm")
    if me:
        d.text((36, h - 46), me["text"], font=get_font(20), fill=(210, 210, 225))
    return _out(img)
