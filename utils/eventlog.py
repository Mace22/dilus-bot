"""Registro de eventos del servidor (entradas, salidas, mensajes, roles, perfil, voz...).

Se guarda en la base de datos para mostrarlo en el panel web (Admin → Logs → Eventos del servidor).
No manda nada a Discord: el canal de `/config logs` lo sigue manejando cogs/warns.py.

Para que no crezca sin límite se conservan como máximo RETENTION_DAYS días y KEEP_PER_GUILD eventos por servidor.
"""
import json
import logging
import time

log = logging.getLogger("dilus-bot.eventlog")

RETENTION_DAYS = 30
KEEP_PER_GUILD = 5000
PRUNE_EVERY = 100        # cada tantos eventos guardados se limpia lo viejo
TEXT_MAX = 1000

# tipo -> (título legible, emoji, categoría)
EVENTS = {
    "member_join": ("Entró al servidor", "📥", "members"),
    "member_leave": ("Salió del servidor", "📤", "members"),
    "member_ban": ("Fue baneado", "🔨", "members"),
    "member_unban": ("Fue desbaneado", "♻️", "members"),
    "timeout_on": ("Timeout aplicado", "🔇", "members"),
    "timeout_off": ("Timeout quitado", "🔊", "members"),
    "message_delete": ("Mensaje borrado", "🗑️", "messages"),
    "message_edit": ("Mensaje editado", "✏️", "messages"),
    "bulk_delete": ("Borrado masivo de mensajes", "🧹", "messages"),
    "role_add": ("Rol agregado", "🏷️", "roles"),
    "role_remove": ("Rol quitado", "🏷️", "roles"),
    "avatar_update": ("Cambió su avatar", "🖼️", "profile"),
    "guild_avatar_update": ("Cambió su avatar del servidor", "🖼️", "profile"),
    "nick_update": ("Cambió su apodo", "📝", "profile"),
    "name_update": ("Cambió su nombre", "📝", "profile"),
    "voice_join": ("Entró a un canal de voz", "🎙️", "voice"),
    "voice_leave": ("Salió de un canal de voz", "🔈", "voice"),
    "voice_move": ("Cambió de canal de voz", "🔀", "voice"),
    "channel_create": ("Canal creado", "➕", "server"),
    "channel_delete": ("Canal borrado", "➖", "server"),
    "channel_update": ("Canal renombrado", "🛠️", "server"),
    "role_create": ("Rol creado", "🆕", "server"),
    "role_delete": ("Rol borrado", "❌", "server"),
}

# categoría -> (nombre, emoji)
CATEGORIES = {
    "members": ("Miembros", "👥"),
    "messages": ("Mensajes", "💬"),
    "roles": ("Roles", "🏷️"),
    "profile": ("Perfil", "🖼️"),
    "voice": ("Voz", "🎙️"),
    "server": ("Servidor", "🛠️"),
}

CDN_PREFIX = "https://cdn.discordapp.com/"
_inserted = 0


def kinds_in(category: str) -> list[str]:
    return [k for k, v in EVENTS.items() if v[2] == category]


def clip(text, limit: int = TEXT_MAX) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def name_of(who) -> str | None:
    """Nombre legible de una persona: 'Apodo (usuario)' si son distintos."""
    if who is None:
        return None
    display = getattr(who, "display_name", None) or str(who)
    username = getattr(who, "name", None)
    return f"{display} ({username})" if username and username != display else display


async def record(bot, guild_id: int, kind: str, *, user=None, channel=None, detail: str = "", **extra):
    """Guarda un evento. Nunca lanza errores: un fallo del registro no puede romper el bot."""
    global _inserted
    try:
        extra = {k: (clip(v) if isinstance(v, str) else v) for k, v in extra.items() if v not in (None, "")}
        await bot.db.execute(
            "INSERT INTO event_log (guild_id, kind, user_id, user_name, channel_id, channel_name, detail, extra, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                guild_id, kind, getattr(user, "id", None), name_of(user),
                getattr(channel, "id", None), getattr(channel, "name", None),
                clip(detail, 300), json.dumps(extra, ensure_ascii=False) if extra else None, time.time(),
            ),
        )
        _inserted += 1
        if _inserted % PRUNE_EVERY == 0:
            await bot.db.execute(
                "DELETE FROM event_log WHERE guild_id = ? AND (ts < ? OR id NOT IN "
                "(SELECT id FROM event_log WHERE guild_id = ? ORDER BY id DESC LIMIT ?))",
                (guild_id, time.time() - RETENTION_DAYS * 86400, guild_id, KEEP_PER_GUILD),
            )
    except Exception:
        log.exception("No pude guardar el evento %s", kind)
