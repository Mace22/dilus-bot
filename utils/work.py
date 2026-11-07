"""Lógica compartida del trabajo (la usan el comando de Discord y la web)."""
import random
import time

WORK_COOLDOWN = 1800          # 30 min entre /trabajar
TASK_COOLDOWN = 600           # 10 min entre /tarea
WORK_BASE = (80, 200)         # pago base de /trabajar (nivel 1)
TASK_BASE = (30, 70)          # pago base de /tarea
LEVEL_BONUS = 0.15            # +15% de paga por cada nivel
XP_WORK, XP_TASK = 3, 1
STREAK_BONUS, STREAK_CAP = 0.05, 10   # tareas seguidas bien: +5% cada una, hasta +50%
EVENTS = [  # (probabilidad, multiplicador, texto)
    (0.03, 3.0, "💎 ¡JACKPOT! Tu jefe te dio un bonus enorme"),
    (0.12, 1.5, "💵 ¡Te dieron propina!"),
]

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
    event, roll, acc = None, random.random(), 0.0
    for prob, m, text in EVENTS:
        acc += prob
        if roll < acc:
            reward, event = int(reward * m), text
            break
    cur = await db.execute(
        "UPDATE economy SET last_work = ? WHERE guild_id = ? AND user_id = ? AND last_work = ?", (now, gid, uid, last)
    )
    if cur.rowcount == 0:
        return "busy", None
    await _pay(db, gid, uid, reward, XP_WORK, "work")
    new = level_of(st["xp"] + XP_WORK)
    return "ok", {"reward": reward, "level": new, "title": title_of(new), "leveled": new > old, "event": event, "ready_at": now + WORK_COOLDOWN}


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
    streak = st["streak"] + 1
    bonus = min(streak - 1, STREAK_CAP) * STREAK_BONUS
    reward = int(random.randint(*TASK_BASE) * mult(old) * (1 + bonus))
    await _pay(db, gid, uid, reward, XP_TASK, "task")
    await db.execute(
        "UPDATE work_stats SET streak = ?, best_streak = MAX(best_streak, ?) WHERE guild_id = ? AND user_id = ?",
        (streak, streak, gid, uid),
    )
    new = level_of(st["xp"] + XP_TASK)
    return {"reward": reward, "level": new, "leveled": new > old, "title": title_of(new), "streak": streak, "bonus": int(bonus * 100)}


async def fail_task(db, gid: int, uid: int):
    await db.execute("UPDATE work_stats SET streak = 0 WHERE guild_id = ? AND user_id = ?", (gid, uid))


async def summary(db, gid: int, uid: int) -> dict:
    st = await get_stats(db, gid, uid)
    lvl = level_of(st["xp"])
    cur, need = progress(st["xp"])
    pos = (await db.fetchone("SELECT COUNT(*) + 1 AS p FROM work_stats WHERE guild_id = ? AND xp > ?", (gid, st["xp"])))["p"] if st["xp"] else None
    return {
        "level": lvl, "title": title_of(lvl), "xp": st["xp"], "xp_in": cur, "xp_need": need,
        "next_title": title_of(lvl + 1) if need else None, "bonus": int(LEVEL_BONUS * 100 * (lvl - 1)),
        "works": st["works"], "tasks": st["tasks"], "earned": st["earned"], "streak": st["streak"],
        "best_streak": st["best_streak"], "rank": pos,
        "task_ready_at": st["last_task"] + TASK_COOLDOWN if st["last_task"] else 0, "task_cooldown": TASK_COOLDOWN,
    }


# ---------------- Puzzles ----------------
WORDS = ["discord", "moneda", "trabajo", "servidor", "teclado", "pantalla", "mensaje", "canal", "ranking", "premio",
         "cofre", "tienda", "jugador", "partida", "ruleta", "nivel", "ventana", "internet", "bandera", "montaña"]
TRIVIA = [
    ("¿Capital de Argentina?", "buenos aires"), ("¿Capital de Francia?", "paris"), ("¿Capital de Japón?", "tokio"),
    ("¿Capital de Italia?", "roma"), ("¿Capital de España?", "madrid"), ("¿Capital de Brasil?", "brasilia"),
    ("¿Capital de Chile?", "santiago"), ("¿Capital de Uruguay?", "montevideo"), ("¿Cuántos días tiene una semana?", "7"),
    ("¿Cuántos lados tiene un hexágono?", "6"), ("¿Cuántos minutos tiene una hora?", "60"), ("¿Cuántos meses tiene un año?", "12"),
    ("¿De qué color es el cielo en un día despejado?", "azul"), ("¿Qué planeta es conocido como el planeta rojo?", "marte"),
    ("¿Cuál es el océano más grande?", "pacifico"), ("¿Cuántos continentes hay?", "7"), ("¿Cuántas patas tiene una araña?", "8"),
]
RIDDLES = [
    ("Tengo agujas pero no pincho. Marco las horas. ¿Qué soy?", "reloj"),
    ("Cuanto más me quitas, más grande soy. ¿Qué soy?", "agujero"),
    ("Vuelo sin alas, lloro sin ojos. ¿Qué soy?", "nube"),
    ("Tiene dientes pero no muerde. ¿Qué es?", "peine"),
    ("Blanca por dentro, verde por fuera. Si quieres que te lo diga, espera. ¿Qué es?", "pera"),
    ("Oro parece, plata no es. ¿Qué es?", "platano"),
]


def _norm(t: str) -> str:
    t = t.strip().lower()
    for a, b in zip("áéíóúüñ", "aeiouun"):
        t = t.replace(a, b)
    return t


def make_puzzle() -> tuple[str, str]:
    """(enunciado, respuesta normalizada)."""
    kind = random.choice(["suma", "mult", "serie", "palabra", "resta", "div", "mayor", "inversa", "falta", "binario",
                          "potencia", "pct", "trivia", "acertijo", "contar", "geom", "par"])
    r = random.randint
    if kind == "suma":
        a, b, c = r(10, 99), r(10, 99), r(10, 99)
        return f"🧮 ¿Cuánto es **{a} + {b} + {c}**?", str(a + b + c)
    if kind == "mult":
        a, b, c = r(3, 12), r(3, 12), r(1, 30)
        return f"🧮 ¿Cuánto es **{a} × {b} + {c}**?", str(a * b + c)
    if kind == "resta":
        a, b, c = r(100, 300), r(10, 99), r(10, 60)
        return f"🧮 ¿Cuánto es **{a} − {b} − {c}**?", str(a - b - c)
    if kind == "div":
        b, q = r(3, 12), r(3, 15)
        return f"➗ ¿Cuánto es **{b * q} ÷ {b}**?", str(q)
    if kind == "potencia":
        a, e = r(2, 9), 2
        return f"🧮 ¿Cuánto es **{a}²**?", str(a * a)
    if kind == "pct":
        p, base = random.choice([10, 20, 25, 50]), random.choice([40, 80, 120, 200, 400])
        return f"💯 ¿Cuánto es el **{p}%** de **{base}**?", str(base * p // 100)
    if kind == "serie":
        s, d = r(1, 20), r(2, 9)
        seq = [s + d * i for i in range(5)]
        return f"🔢 Completá la serie: **{', '.join(map(str, seq[:4]))}, ?**", str(seq[4])
    if kind == "geom":
        s, m = r(1, 4), r(2, 3)
        seq = [s * m ** i for i in range(5)]
        return f"🔢 Completá la serie: **{', '.join(map(str, seq[:4]))}, ?**", str(seq[4])
    if kind == "mayor":
        nums = random.sample(range(1, 200), 5)
        return f"📈 ¿Cuál es el **mayor** número? **{', '.join(map(str, nums))}**", str(max(nums))
    if kind == "par":
        nums = random.sample(range(1, 60), 8)
        return f"🔢 ¿Cuántos números **pares** hay? **{', '.join(map(str, nums))}**", str(sum(n % 2 == 0 for n in nums))
    if kind == "binario":
        n = r(2, 15)
        return f"💻 ¿Cuánto es **{bin(n)[2:]}** en binario pasado a decimal?", str(n)
    if kind == "inversa":
        w = random.choice(WORDS)
        return f"🪞 Escribí al revés la palabra: **{w.upper()}**", w[::-1]
    if kind == "falta":
        w = random.choice(WORDS)
        i = r(1, len(w) - 2)
        return f"🔠 ¿Qué letra falta? **{w[:i].upper()}_{w[i + 1:].upper()}**", _norm(w[i])
    if kind == "contar":
        w, ch = random.choice(WORDS), None
        ch = random.choice(w)
        return f"🔍 ¿Cuántas veces aparece la letra **{ch.upper()}** en **{w.upper()}**?", str(w.count(ch))
    if kind == "trivia":
        q, a = random.choice(TRIVIA)
        return f"🌍 {q}", a
    if kind == "acertijo":
        q, a = random.choice(RIDDLES)
        return f"🧩 {q}", a
    w = random.choice(WORDS)
    letters = list(w)
    for _ in range(10):
        random.shuffle(letters)
        if "".join(letters) != w:
            break
    return f"🔤 Ordená las letras para formar una palabra: **{' '.join(letters).upper()}**", w


def check(answer: str, expected: str) -> bool:
    return _norm(answer) == _norm(expected)
