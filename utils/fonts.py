import os
from functools import lru_cache

from PIL import ImageDraw, ImageFont

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")

# Fuente incluida en el proyecto (soporta tildes, ñ, ¡ ¿). Si faltara, se prueban fuentes del sistema.
CANDIDATES = [
    os.path.join(_ASSETS, "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


@lru_cache(maxsize=64)
def get_font(size: int):
    for path in CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 14):
    """Devuelve la fuente más grande (hasta start_size) con la que el texto entra en max_width."""
    size = start_size
    while size > min_size:
        font = get_font(size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 2
    return get_font(min_size)
