"""Cofres: configuración central y reglas puras (sin Discord ni base de datos).

>>> TODO lo que se puede ajustar de los cofres está en este archivo. <<<
Los admins además pueden cambiar los precios y una "escala" global de recompensas con /cofreadmin (se guarda en la base).
"""
import random

# ----------------------------------------------------------------------
# Tiempos
# ----------------------------------------------------------------------
COOLDOWN = 24 * 3600          # segundos entre dos cofres gratis (se puede reclamar justo a las 24 h exactas)
STREAK_WINDOW = 48 * 3600     # si pasan 48 h o más desde el último cofre, la racha se pierde
                              # (se usan relojes de 24 h corridas, no días de calendario: no dependen de zonas horarias)

# Cofre que toca según el día de racha. Pasado el día 7 se mantiene el último (legendario).
STREAK_PROGRESSION = ["common", "common", "rare", "rare", "epic", "epic", "legendary"]

MAX_BUY_QTY = 10              # tope de cofres por compra

# ----------------------------------------------------------------------
# Precios de los cofres comprables (el admin los puede cambiar con /cofreadmin precio)
# ----------------------------------------------------------------------
DEFAULT_PRICES = {"common": 100, "rare": 200, "epic": 400, "legendary": 600}

# ----------------------------------------------------------------------
# Recompensas: SOLO monedas.  Cada cofre es una lista de tramos (peso %, mínimo, máximo).
# Se sortea primero el tramo según el peso y después una cantidad al azar dentro del tramo.
# Valor esperado (promedio): común ≈ 82, raro ≈ 167, épico ≈ 314, legendario ≈ 472 monedas.
# Comprarlos devuelve ≈ 78-83 % de lo que cuestan: así comprar cofres NO fabrica monedas (las quita de circulación).
# ----------------------------------------------------------------------
REWARDS = {
    "common":    [(48, 30, 65), (28, 65, 100), (15, 100, 140), (7, 140, 210), (2, 210, 320)],
    "rare":      [(46, 80, 130), (28, 130, 185), (15, 185, 260), (8, 260, 380), (3, 380, 640)],
    "epic":      [(45, 150, 240), (28, 240, 340), (15, 340, 480), (9, 480, 700), (3, 700, 1300)],
    "legendary": [(44, 250, 380), (28, 380, 500), (15, 500, 650), (9, 650, 900), (4, 900, 1800)],
}
SEGMENT_NAMES = ["Básico", "Bueno", "Muy bueno", "Excelente", "¡Jackpot!"]          # nombre de cada tramo (igual para todos los cofres)
SEGMENT_COLORS = ["#9ca3af", "#60a5fa", "#a78bfa", "#f472b6", "#fbbf24"]            # color de cada tramo en la ruleta

# ----------------------------------------------------------------------
# Presentación
# ----------------------------------------------------------------------
RARITIES = ("common", "rare", "epic", "legendary")
RARITY_NAME = {"common": "Común", "rare": "Raro", "epic": "Épico", "legendary": "Legendario"}
RARITY_EMOJI = {"common": "📦", "rare": "🔷", "epic": "🔮", "legendary": "👑"}
RARITY_COLOR = {"common": 0x9CA3AF, "rare": 0x3B82F6, "epic": 0x8B5CF6, "legendary": 0xF5B301}
RARITY_HEX = {r: f"#{c:06x}" for r, c in RARITY_COLOR.items()}

SCALE_MIN, SCALE_MAX = 0.25, 4.0
PRICE_MIN, PRICE_MAX = 1, 1_000_000


# ----------------------------------------------------------------------
# Reglas puras
# ----------------------------------------------------------------------
def r5(x: float) -> int:
    """Redondea a múltiplos de 5 (con mínimo 5) para que las cantidades queden prolijas."""
    return max(5, int(round(x / 5.0)) * 5)


def segments(rarity: str, scale: float = 1.0) -> list[dict]:
    """Tramos de un cofre con la escala aplicada y el porcentaje de cada uno."""
    table = REWARDS[rarity]
    total = sum(w for w, _, _ in table)
    out = []
    for i, (w, lo, hi) in enumerate(table):
        lo_s, hi_s = r5(lo * scale), r5(hi * scale)
        out.append({"index": i, "name": SEGMENT_NAMES[i], "color": SEGMENT_COLORS[i], "weight": w, "pct": round(w / total * 100, 1),
                    "lo": lo_s, "hi": max(lo_s, hi_s)})
    return out


def expected_value(rarity: str, scale: float = 1.0) -> float:
    segs = segments(rarity, scale)
    total = sum(s["weight"] for s in segs)
    return sum(s["weight"] * (s["lo"] + s["hi"]) / 2 for s in segs) / total


def draw_reward(rarity: str, scale: float = 1.0, rng: random.Random | None = None) -> tuple[int, int]:
    """Sortea la recompensa. Devuelve (índice del tramo, monedas). Se llama SIEMPRE en el servidor."""
    rng = rng or random.SystemRandom()
    segs = segments(rarity, scale)
    pick = rng.random() * sum(s["weight"] for s in segs)
    acc, chosen = 0.0, segs[-1]
    for s in segs:
        acc += s["weight"]
        if pick < acc:
            chosen = s
            break
    amount = r5(rng.randint(chosen["lo"], chosen["hi"]))
    return chosen["index"], min(chosen["hi"], max(chosen["lo"], amount))


def rarity_for_streak(streak: int) -> str:
    return STREAK_PROGRESSION[min(max(streak, 1), len(STREAK_PROGRESSION)) - 1]


def streak_status(last_claim: float, streak: int, now: float) -> dict:
    """Estado del cofre diario. Todo se calcula con relojes de 24 h corridas (UTC), nunca con el calendario local."""
    if last_claim <= 0:
        return {"streak": 0, "alive": False, "available": True, "ready_at": 0.0, "expires_at": None, "next_streak": 1}
    elapsed = now - last_claim
    alive = elapsed < STREAK_WINDOW
    return {
        "streak": streak if alive else 0,
        "alive": alive,
        "available": elapsed >= COOLDOWN,
        "ready_at": last_claim + COOLDOWN,
        "expires_at": last_claim + STREAK_WINDOW if alive else None,
        "next_streak": streak + 1 if alive else 1,
    }
