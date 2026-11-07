"""Lógica compartida del trabajo (la usan el comando de Discord y la web)."""
import random
import time

WORK_COOLDOWN = 1800          # 30 min entre /trabajar
TASK_COOLDOWN = 600           # 10 min entre /tarea
WORK_BASE = (80, 200)         # pago base de /trabajar (nivel 1)
TASK_BASE = (30, 70)          # pago base de /tarea
LEVEL_BONUS = 0.15            # +15% de paga por cada nivel
XP_WORK, XP_TASK = 3, 1

# (xp necesaria, título)
LEVELS = [
    (0, "Pasante"), (10, "Junior"), (30, "Empleado"), (65, "Semi-senior"), (120, "Senior"),
    (200, "Encargado"), (320, "Supervisor"), (480, "Gerente"), (700, "Director"), (1000, "Magnate"),
]



def level_of(xp: int) -> int:
    lvl = 1
    for i, (need, _) in enumerate(LEVELS):
        if xp >= need:
            lvl = i + 1
    return lvl


def title_of(level: int) -> str:
    return LEVELS[level - 1][1]


def mult(level: int) -> float:
    return 1 + LEVEL_BONUS * (level - 1)


def progress(xp: int) -> tuple[int, int | None]:
    """(xp en el nivel actual, xp que falta para el siguiente o None si es nivel máximo)."""
    lvl = level_of(xp)
    if lvl >= len(LEVELS):
        return xp - LEVELS[-1][0], None
    return xp - LEVELS[lvl - 1][0], LEVELS[lvl][0] - LEVELS[lvl - 1][0]


async def get_stats(db, gid: int, uid: int):
    await db.execute("INSERT OR IGNORE INTO work_stats (guild_id, user_id) VALUES (?, ?)", (gid, uid))
    return await db.fetchone("SELECT * FROM work_stats WHERE guild_id = ? AND user_id = ?", (gid, uid))


async def _pay(db, gid, uid, reward, xp, kind):
    col = "works" if kind == "work" else "tasks"
    await db.execute(f"UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (reward, gid, uid))
    await db.execute(
        f"UPDATE work_stats SET xp = xp + ?, {col} = {col} + 1, earned = earned + ? WHERE guild_id = ? AND user_id = ?",
        (xp, reward, gid, uid),
    )


async def do_work(db, gid: int, uid: int):
    """Devuelve ('cooldown', ready_at) | ('busy', None) | ('ok', dict)."""
    await db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", (gid, uid))
    row = await db.fetchone("SELECT last_work FROM economy WHERE guild_id = ? AND user_id = ?", (gid, uid))
    st = await get_stats(db, gid, uid)
    now, last = time.time(), row["last_work"]
    if now - last < WORK_COOLDOWN:
        return "cooldown", last + WORK_COOLDOWN
    old = level_of(st["xp"])
    reward = int(random.randint(*WORK_BASE) * mult(old))
    cur = await db.execute(
        "UPDATE economy SET last_work = ? WHERE guild_id = ? AND user_id = ? AND last_work = ?", (now, gid, uid, last)
    )
    if cur.rowcount == 0:
        return "busy", None
    await _pay(db, gid, uid, reward, XP_WORK, "work")
    new = level_of(st["xp"] + XP_WORK)
    return "ok", {"reward": reward, "level": new, "title": title_of(new), "leveled": new > old, "ready_at": now + WORK_COOLDOWN}


async def start_task(db, gid: int, uid: int):
    """Reserva el cooldown de la tarea. Devuelve ('cooldown', ready_at) | ('ok', None)."""
    st = await get_stats(db, gid, uid)
    now, last = time.time(), st["last_task"]
    if now - last < TASK_COOLDOWN:
        return "cooldown", last + TASK_COOLDOWN
    cur = await db.execute(
        "UPDATE work_stats SET last_task = ? WHERE guild_id = ? AND user_id = ? AND last_task = ?", (now, gid, uid, last)
    )
    return ("ok", None) if cur.rowcount else ("cooldown", now + TASK_COOLDOWN)


async def finish_task(db, gid: int, uid: int) -> dict:
    st = await get_stats(db, gid, uid)
    old = level_of(st["xp"])
    reward = int(random.randint(*TASK_BASE) * mult(old))
    await _pay(db, gid, uid, reward, XP_TASK, "task")
    new = level_of(st["xp"] + XP_TASK)
    return {"reward": reward, "level": new, "leveled": new > old, "title": title_of(new)}


# ---------------- Puzzles ----------------
WORDS = ["discord", "moneda", "trabajo", "servidor", "teclado", "pantalla", "mensaje", "canal", "ranking", "premio",
         "cofre", "tienda", "jugador", "partida", "ruleta", "nivel"]


def make_puzzle() -> tuple[str, str]:
    """(enunciado, respuesta normalizada)."""
    kind = random.choice(["suma", "mult", "serie", "palabra"])
    if kind == "suma":
        a, b, c = random.randint(10, 99), random.randint(10, 99), random.randint(10, 99)
        return f"🧮 ¿Cuánto es **{a} + {b} + {c}**?", str(a + b + c)
    if kind == "mult":
        a, b, c = random.randint(3, 12), random.randint(3, 12), random.randint(1, 30)
        return f"🧮 ¿Cuánto es **{a} × {b} + {c}**?", str(a * b + c)
    if kind == "serie":
        s, d = random.randint(1, 20), random.randint(2, 9)
        seq = [s + d * i for i in range(5)]
        return f"🔢 Completá la serie: **{', '.join(map(str, seq[:4]))}, ?**", str(seq[4])
    w = random.choice(WORDS)
    letters = list(w)
    for _ in range(10):
        random.shuffle(letters)
        if "".join(letters) != w:
            break
    return f"🔤 Ordená las letras para formar una palabra: **{' '.join(letters).upper()}**", w


def check(answer: str, expected: str) -> bool:
    return answer.strip().lower() == expected
