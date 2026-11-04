"""Registro de acciones de administración (panel web y comandos). Queda guardado y se ve en el panel de Admin."""
import logging
import time

import discord

from utils.embeds import make_embed

log = logging.getLogger("dilus-bot.adminlog")

# acción -> (título legible, emoji, categoría)
ACTIONS = {
    "coins_give": ("Dio monedas", "💰", "economy"),
    "coins_take": ("Quitó monedas", "💸", "economy"),
    "shop_add": ("Agregó rol a la tienda", "🛒", "economy"),
    "shop_remove": ("Sacó rol de la tienda", "🛒", "economy"),
    "warn": ("Advirtió", "⚠️", "moderation"),
    "clearwarns": ("Borró advertencias", "🧹", "moderation"),
    "timeout": ("Aplicó timeout", "🔇", "moderation"),
    "untimeout": ("Quitó timeout", "🔊", "moderation"),
    "kick": ("Expulsó", "👢", "moderation"),
    "ban": ("Baneó", "🔨", "moderation"),
}
KEEP_PER_GUILD = 1000


def actions_in(category: str) -> list[str]:
    return [k for k, v in ACTIONS.items() if v[2] == category]


async def record(bot, guild: discord.Guild, *, actor, action: str, target=None, amount: int | None = None,
                 detail: str = "", source: str = "discord"):
    """Guarda la acción en la base y la avisa en el canal de logs del servidor (si hay uno configurado)."""
    try:
        t_id = getattr(target, "id", target)
        t_name = getattr(target, "display_name", None) or (str(target) if target is not None else None)
        await bot.db.execute(
            "INSERT INTO admin_log (guild_id, actor_id, actor_name, action, target_id, target_name, amount, detail, source, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (guild.id, actor.id, actor.display_name, action, t_id, t_name, amount, (detail or "")[:300], source, time.time()),
        )
        await bot.db.execute(
            "DELETE FROM admin_log WHERE guild_id = ? AND id NOT IN (SELECT id FROM admin_log WHERE guild_id = ? ORDER BY id DESC LIMIT ?)",
            (guild.id, guild.id, KEEP_PER_GUILD),
        )
    except Exception:
        log.exception("No pude guardar la acción de admin en el registro")
        return

    title, emoji, _ = ACTIONS.get(action, (action, "🛠️", "other"))
    embed = make_embed(f"{emoji} {title}", color=0xF59E0B)
    embed.add_field(name="Admin", value=f"{actor.mention if hasattr(actor, 'mention') else actor}  ({'panel web' if source == 'web' else 'Discord'})")
    if target is not None:
        embed.add_field(name="Persona", value=getattr(target, "mention", None) or t_name)
    if amount is not None:
        embed.add_field(name="Monto", value=f"{amount:+,}".replace(",", "."))
    if detail:
        embed.add_field(name="Detalle", value=detail[:300], inline=False)
    warns = bot.get_cog("Warns")
    if warns is not None:
        await warns.send_log(guild, embed)
