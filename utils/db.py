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
