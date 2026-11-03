import os

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS levels (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 0,
    messages INTEGER NOT NULL DEFAULT 0,
    voice_seconds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS level_roles (
    guild_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    welcome_channel INTEGER,
    goodbye_channel INTEGER,
    autorole INTEGER,
    levelup_channel INTEGER,
    voice_channel INTEGER,
    ticket_category INTEGER,
    ticket_staff_role INTEGER,
    log_channel INTEGER,
    tempvoice_channel INTEGER
);

CREATE TABLE IF NOT EXISTS giveaways (
    message_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    host_id INTEGER NOT NULL,
    prize TEXT NOT NULL,
    winners INTEGER NOT NULL DEFAULT 1,
    end_time REAL NOT NULL,
    ended INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS giveaway_entries (
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (message_id, user_id)
);

CREATE TABLE IF NOT EXISTS economy (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0,
    last_daily REAL NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_work REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS shop (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    price INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS temp_voice (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL
);

-- Apuestas de la ruleta que todavía no se resolvieron (si el bot se reinicia, se devuelven)
CREATE TABLE IF NOT EXISTS roulette_bets (
    message_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    bet_key TEXT NOT NULL,
    amount INTEGER NOT NULL,
    PRIMARY KEY (message_id, user_id, bet_key)
);

-- Panel web: manos de blackjack abiertas (si el bot se reinicia, se devuelven)
CREATE TABLE IF NOT EXISTS web_blackjack (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    bet INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

-- Panel web: estadísticas de casino por persona
CREATE TABLE IF NOT EXISTS casino_stats (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    game TEXT NOT NULL,
    played INTEGER NOT NULL DEFAULT 0,
    wagered INTEGER NOT NULL DEFAULT 0,
    returned INTEGER NOT NULL DEFAULT 0,
    best INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, game)
);

-- Panel web: últimas jugadas (para el historial y el gráfico de ganancias)
CREATE TABLE IF NOT EXISTS casino_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    game TEXT NOT NULL,
    bet INTEGER NOT NULL,
    returned INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_casino_log_user ON casino_log (guild_id, user_id, id);

-- ======================================================================
-- Libro de movimientos de la economía (idempotente).
-- Un movimiento se identifica con "ref": si se intenta aplicar dos veces la misma ref, la segunda se ignora.
-- El saldo se actualiza en el mismo instante (trigger), así que mover monedas y dejar constancia es UNA sola operación atómica.
-- ======================================================================
CREATE TABLE IF NOT EXISTS economy_ledger (
    ref TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL
);
CREATE TRIGGER IF NOT EXISTS trg_ledger_funds BEFORE INSERT ON economy_ledger
WHEN NEW.delta < 0 AND COALESCE((SELECT balance FROM economy WHERE guild_id = NEW.guild_id AND user_id = NEW.user_id), 0) + NEW.delta < 0
BEGIN
    SELECT RAISE(ABORT, 'insufficient_funds');
END;
CREATE TRIGGER IF NOT EXISTS trg_ledger_apply AFTER INSERT ON economy_ledger
BEGIN
    INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (NEW.guild_id, NEW.user_id);
    UPDATE economy SET balance = balance + NEW.delta WHERE guild_id = NEW.guild_id AND user_id = NEW.user_id;
END;

-- ======================================================================
-- Cofres (diarios y comprables)
-- ======================================================================
CREATE TABLE IF NOT EXISTS chest_state (            -- racha del cofre diario (independiente del /daily)
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    last_claim REAL NOT NULL DEFAULT 0,
    claims INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS chest_inventory (        -- cofres comprados que todavía no se abrieron
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rarity TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 0 CHECK (qty >= 0),
    PRIMARY KEY (guild_id, user_id, rarity)
);
CREATE TABLE IF NOT EXISTS chest_opens (            -- historial: cada apertura tiene un id único (open_id)
    open_id TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rarity TEXT NOT NULL CHECK (rarity IN ('common', 'rare', 'epic', 'legendary')),
    source TEXT NOT NULL CHECK (source IN ('daily', 'bought')),
    reward INTEGER NOT NULL CHECK (reward > 0),
    segment INTEGER NOT NULL,
    streak_after INTEGER NOT NULL DEFAULT 0,
    prev_claim REAL NOT NULL DEFAULT 0,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chest_opens_user ON chest_opens (guild_id, user_id, ts);
CREATE TABLE IF NOT EXISTS chest_purchases (        -- compras (id = identificador de la solicitud: reintentos no cobran dos veces)
    id TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rarity TEXT NOT NULL CHECK (rarity IN ('common', 'rare', 'epic', 'legendary')),
    qty INTEGER NOT NULL CHECK (qty > 0),
    unit_price INTEGER NOT NULL CHECK (unit_price > 0),
    total INTEGER NOT NULL CHECK (total > 0),
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chest_purchases_user ON chest_purchases (guild_id, user_id, ts);
CREATE TABLE IF NOT EXISTS chest_settings (         -- ajustes que cambian los admins (precios, escala de recompensas)
    guild_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (guild_id, key)
);

-- Abrir un cofre es UNA sola sentencia (INSERT en chest_opens). Estos triggers hacen, dentro de esa misma sentencia:
--   1) validar que se puede abrir (cooldown/estado desactualizado o falta de stock),
--   2) consumir el cofre (actualizar la racha o descontar del inventario),
--   3) acreditar las monedas en el libro de la economía.
-- Si cualquier paso falla, no se aplica NINGUNO (ni racha, ni cofre, ni monedas).
CREATE TRIGGER IF NOT EXISTS trg_open_guard_daily BEFORE INSERT ON chest_opens
WHEN NEW.source = 'daily' AND NOT EXISTS (
    SELECT 1 FROM chest_state WHERE guild_id = NEW.guild_id AND user_id = NEW.user_id AND last_claim = NEW.prev_claim)
BEGIN
    SELECT RAISE(ABORT, 'stale_state');
END;
CREATE TRIGGER IF NOT EXISTS trg_open_guard_bought BEFORE INSERT ON chest_opens
WHEN NEW.source = 'bought' AND NOT EXISTS (
    SELECT 1 FROM chest_inventory WHERE guild_id = NEW.guild_id AND user_id = NEW.user_id AND rarity = NEW.rarity AND qty >= 1)
BEGIN
    SELECT RAISE(ABORT, 'no_stock');
END;
CREATE TRIGGER IF NOT EXISTS trg_open_apply_daily AFTER INSERT ON chest_opens
WHEN NEW.source = 'daily'
BEGIN
    UPDATE chest_state
       SET streak = NEW.streak_after, best_streak = MAX(best_streak, NEW.streak_after), last_claim = NEW.ts, claims = claims + 1
     WHERE guild_id = NEW.guild_id AND user_id = NEW.user_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_open_apply_bought AFTER INSERT ON chest_opens
WHEN NEW.source = 'bought'
BEGIN
    UPDATE chest_inventory SET qty = qty - 1 WHERE guild_id = NEW.guild_id AND user_id = NEW.user_id AND rarity = NEW.rarity;
END;
CREATE TRIGGER IF NOT EXISTS trg_open_credit AFTER INSERT ON chest_opens
BEGIN
    INSERT INTO economy_ledger (ref, guild_id, user_id, delta, kind, ts)
    VALUES ('chest:' || NEW.open_id, NEW.guild_id, NEW.user_id, NEW.reward, 'chest_reward', NEW.ts);
END;
-- Comprar un cofre también es UNA sola sentencia: cobra (libro) + suma al inventario. Sin saldo, no pasa nada.
CREATE TRIGGER IF NOT EXISTS trg_purchase_apply AFTER INSERT ON chest_purchases
BEGIN
    INSERT INTO economy_ledger (ref, guild_id, user_id, delta, kind, ts)
    VALUES ('buy:' || NEW.id, NEW.guild_id, NEW.user_id, -NEW.total, 'chest_purchase', NEW.ts);
    INSERT INTO chest_inventory (guild_id, user_id, rarity, qty) VALUES (NEW.guild_id, NEW.user_id, NEW.rarity, NEW.qty)
    ON CONFLICT (guild_id, user_id, rarity) DO UPDATE SET qty = qty + NEW.qty;
END;
"""

# Columnas agregadas después de la primera versión (se añaden solas a bases ya existentes)
MIGRATIONS = {
    "log_channel": "INTEGER",
    "tempvoice_channel": "INTEGER",
}

# Columnas permitidas en guild_settings (evita inyección SQL en set_setting)
SETTINGS = {
    "welcome_channel",
    "goodbye_channel",
    "autorole",
    "levelup_channel",
    "voice_channel",
    "ticket_category",
    "ticket_staff_role",
    "log_channel",
    "tempvoice_channel",
}


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self._migrate()
        await self.conn.commit()

    async def _migrate(self):
        """Agrega columnas nuevas a tablas que ya existían (sin perder datos)."""
        async with self.conn.execute("PRAGMA table_info(guild_settings)") as cur:
            existing = {row["name"] for row in await cur.fetchall()}
        for column, col_type in MIGRATIONS.items():
            if column not in existing:
                await self.conn.execute(f"ALTER TABLE guild_settings ADD COLUMN {column} {col_type}")

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def execute(self, sql: str, params: tuple = ()):
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur

    async def fetchone(self, sql: str, params: tuple = ()):
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()):
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchall()

    # ---- ajustes por servidor ----
    async def get_setting(self, guild_id: int, key: str):
        if key not in SETTINGS:
            raise ValueError(f"Ajuste desconocido: {key}")
        row = await self.fetchone(f"SELECT {key} FROM guild_settings WHERE guild_id = ?", (guild_id,))
        return row[key] if row else None

    async def set_setting(self, guild_id: int, key: str, value):
        if key not in SETTINGS:
            raise ValueError(f"Ajuste desconocido: {key}")
        await self.execute(
            f"INSERT INTO guild_settings (guild_id, {key}) VALUES (?, ?) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {key} = excluded.{key}",
            (guild_id, value),
        )
