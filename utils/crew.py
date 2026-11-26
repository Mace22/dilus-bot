"""Ingreso de nuevos miembros y rol Crew.

Cuando alguien entra, el bot avisa en el canal de ingresos y el staff puede darle el rol Crew reaccionando con ✅.
Quién cuenta como staff: Administrador, Gestionar roles, o el rol de staff que se configure (opcional).
"""
import discord

CHECK = "✅"
SETTINGS_KEYS = ("crew_channel", "crew_role", "crew_staff_role")
NOTICE_KEEP_DAYS = 60


def role_problem(guild: discord.Guild, role: discord.Role) -> str | None:
    """Por qué el bot no puede dar este rol como Crew (None si está todo bien)."""
    me = guild.me
    if role.is_default():
        return "No puede ser @everyone."
    if role.managed:
        return "Ese rol lo maneja una integración o un bot, no se puede asignar a mano."
    if role.permissions.administrator:
        return "Ese rol tiene permiso de Administrador. Por seguridad el Crew no puede tenerlo: se da con una sola reacción."
    if not me.guild_permissions.manage_roles:
        return "Me falta el permiso **Gestionar roles**."
    if role >= me.top_role:
        return "Ese rol está por encima del mío. Subí mi rol en Ajustes del servidor → Roles."
    return None


def channel_problem(channel: discord.TextChannel, me: discord.Member) -> str | None:
    """Permisos que necesita el bot en el canal de ingresos."""
    perms = channel.permissions_for(me)
    missing = [
        name for name, ok in (
            ("Ver canal", perms.view_channel), ("Enviar mensajes", perms.send_messages),
            ("Insertar enlaces", perms.embed_links), ("Añadir reacciones", perms.add_reactions),
            ("Leer el historial", perms.read_message_history),
        ) if not ok
    ]
    return f"Me faltan permisos en {channel.mention}: {', '.join(missing)}." if missing else None


def is_staff(member: discord.Member, staff_role_id: int | None) -> bool:
    perms = member.guild_permissions
    if perms.administrator or perms.manage_roles:
        return True
    return bool(staff_role_id and any(r.id == staff_role_id for r in member.roles))
