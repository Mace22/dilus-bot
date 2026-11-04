"""Tags de colores: roles de Discord con color que se compran con monedas.

La lógica vive acá y la usan tanto los comandos (/tags ...) como el panel web.
Los roles los crea el bot solo la primera vez que alguien compra ese color.
"""
import asyncio
import logging
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from cogs.economy import COIN, fmt
from utils.embeds import error, make_embed, ok

log = logging.getLogger("dilus-bot.tags")

TAG_PREFIX = "Tag "


@dataclass(frozen=True)
class Tag:
    key: str
    name: str
    emoji: str
    color: int
    price: int

    @property
    def role_name(self) -> str:
        return f"{TAG_PREFIX}{self.name}"

    @property
    def hex(self) -> str:
        return f"#{self.color:06x}"


# ---------- Catálogo (tocá nombres, colores y precios a gusto) ----------
# OJO: Discord trata el color 0x000000 como "sin color", por eso el negro es 0x010101.
TAGS: list[Tag] = [
    Tag("negro",    "Negro",    "⚫", 0x010101, 10_000),
    Tag("dorado",   "Dorado",   "🟡", 0xFFC400, 5_000),
    Tag("rojo",     "Rojo",     "🔴", 0xE11D48, 4_500),
    Tag("violeta",  "Violeta",  "🟣", 0x8B5CF6, 4_000),
    Tag("celeste",  "Celeste",  "🔵", 0x38BDF8, 3_500),
    Tag("verde",    "Verde",    "🟢", 0x22C55E, 3_000),
    Tag("naranja",  "Naranja",  "🟠", 0xFB923C, 2_500),
    Tag("rosa",     "Rosa",     "🌸", 0xF472B6, 2_000),
    Tag("blanco",   "Blanco",   "⚪", 0xFFFFFF, 1_500),
]
# -------------------------------------------------------------------------
BY_KEY = {t.key: t for t in TAGS}


class TagError(Exception):
    """Error con mensaje listo para mostrar (status = código HTTP equivalente para el panel)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class Tags(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._user_locks: dict[tuple[int, int], asyncio.Lock] = {}
        self._guild_locks: dict[int, asyncio.Lock] = {}

    @property
    def eco(self):
        eco = self.bot.get_cog("Economy")
        if eco is None:
            raise TagError("La economía del bot no está activa.", 503)
        return eco

    def _ulock(self, gid: int, uid: int) -> asyncio.Lock:
        if len(self._user_locks) > 5000:
            self._user_locks = {k: v for k, v in self._user_locks.items() if v.locked()}
        return self._user_locks.setdefault((gid, uid), asyncio.Lock())

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------
    async def _role_for(self, guild: discord.Guild, tag: Tag, *, create: bool) -> discord.Role | None:
        row = await self.bot.db.fetchone("SELECT role_id FROM tag_roles WHERE guild_id = ? AND tag = ?", (guild.id, tag.key))
        role = guild.get_role(row["role_id"]) if row else None
        if role or not create:
            return role

        async with self._guild_locks.setdefault(guild.id, asyncio.Lock()):
            row = await self.bot.db.fetchone("SELECT role_id FROM tag_roles WHERE guild_id = ? AND tag = ?", (guild.id, tag.key))
            role = guild.get_role(row["role_id"]) if row else None
            if role:
                return role
            if not guild.me.guild_permissions.manage_roles:
                raise TagError("Me falta el permiso «Gestionar roles» para crear el tag.", 409)
            try:
                role = await guild.create_role(
                    name=tag.role_name, colour=discord.Colour(tag.color), hoist=False, mentionable=False,
                    reason="Tag de color - Dilu's Bot",
                )
            except discord.HTTPException:
                raise TagError("No pude crear el rol del tag. Revisá mis permisos.", 500)
            try:   # lo subo lo más posible (justo debajo del rol del bot) para que el color se vea por encima de otros roles
                top = guild.me.top_role.position - 1
                if top > 0:
                    await role.edit(position=top, reason="Tag de color - Dilu's Bot")
            except discord.HTTPException:
                log.warning("No pude subir el rol %s en %s", role.name, guild.name)
            await self.bot.db.execute(
                "INSERT INTO tag_roles (guild_id, tag, role_id) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, tag) DO UPDATE SET role_id = excluded.role_id",
                (guild.id, tag.key, role.id),
            )
            return role

    async def _tag_roles_of(self, member: discord.Member) -> list[discord.Role]:
        rows = await self.bot.db.fetchall("SELECT role_id FROM tag_roles WHERE guild_id = ?", (member.guild.id,))
        ids = {r["role_id"] for r in rows}
        return [r for r in member.roles if r.id in ids]

    async def _owned(self, gid: int, uid: int) -> set[str]:
        rows = await self.bot.db.fetchall("SELECT tag FROM tag_owned WHERE guild_id = ? AND user_id = ?", (gid, uid))
        return {r["tag"] for r in rows}

    async def _equip(self, member: discord.Member, tag: Tag):
        """Le deja puesto solo este tag (saca los otros de color)."""
        role = await self._role_for(member.guild, tag, create=True)
        if role >= member.guild.me.top_role:
            raise TagError("No puedo darte ese tag (el rol quedó por encima del mío).", 409)
        others = [r for r in await self._tag_roles_of(member) if r.id != role.id]
        try:
            if others:
                await member.remove_roles(*others, reason="Cambio de tag - Dilu's Bot")
            if role not in member.roles:
                await member.add_roles(role, reason="Tag de color - Dilu's Bot")
        except discord.HTTPException:
            raise TagError("No pude darte el rol del tag. Revisá mis permisos.", 500)

    # ------------------------------------------------------------------
    # API común (comandos y panel)
    # ------------------------------------------------------------------
    @staticmethod
    def _get(key) -> Tag:
        tag = BY_KEY.get(key) if isinstance(key, str) else None
        if tag is None:
            raise TagError("Ese tag no existe.", 404)
        return tag

    async def catalog(self, guild: discord.Guild, member: discord.Member | None) -> list[dict]:
        owned = await self._owned(guild.id, member.id) if member else set()
        worn = {r.id for r in member.roles} if member else set()
        items = []
        for t in sorted(TAGS, key=lambda x: -x.price):
            role = await self._role_for(guild, t, create=False)
            items.append({
                "key": t.key, "name": t.name, "emoji": t.emoji, "color": t.hex, "price": t.price,
                "owned": t.key in owned, "equipped": bool(role and role.id in worn),
            })
        return items

    async def buy(self, guild: discord.Guild, member: discord.Member, key) -> Tag:
        tag = self._get(key)
        async with self._ulock(guild.id, member.id):
            if tag.key in await self._owned(guild.id, member.id):
                raise TagError("Ya tenés ese tag. Usalo con /tags usar.", 409)
            await self._role_for(guild, tag, create=True)      # si falla, todavía no se cobró nada
            if not await self.eco.add(guild.id, member.id, -tag.price):
                raise TagError("No tenés suficientes monedas.", 402)
            try:
                await self._equip(member, tag)
            except TagError:
                await self.eco.add(guild.id, member.id, tag.price)   # devolución
                raise
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO tag_owned (guild_id, user_id, tag) VALUES (?, ?, ?)", (guild.id, member.id, tag.key)
            )
        return tag

    async def equip(self, guild: discord.Guild, member: discord.Member, key) -> Tag:
        tag = self._get(key)
        async with self._ulock(guild.id, member.id):
            if tag.key not in await self._owned(guild.id, member.id):
                raise TagError("Todavía no compraste ese tag.", 409)
            await self._equip(member, tag)
        return tag

    async def unequip(self, member: discord.Member):
        async with self._ulock(member.guild.id, member.id):
            roles = await self._tag_roles_of(member)
            if not roles:
                raise TagError("No tenés ningún tag puesto.", 409)
            try:
                await member.remove_roles(*roles, reason="Tag sacado - Dilu's Bot")
            except discord.HTTPException:
                raise TagError("No pude sacarte el tag. Revisá mis permisos.", 500)

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------
    tags = app_commands.Group(name="tags", description="Tags de colores para tu nombre", guild_only=True)

    CHOICES = [app_commands.Choice(name=f"{t.emoji} {t.name} — {fmt(t.price)}", value=t.key) for t in sorted(TAGS, key=lambda x: -x.price)]

    @tags.command(name="lista", description="Mirá los tags de colores disponibles y cuáles tenés")
    async def tags_list(self, interaction: discord.Interaction):
        items = await self.catalog(interaction.guild, interaction.user)
        lines = []
        for it in items:
            state = "  ✅ **puesto**" if it["equipped"] else "  📦 comprado" if it["owned"] else ""
            lines.append(f"{it['emoji']} **{it['name']}** — {fmt(it['price'])} {COIN}{state}")
        embed = make_embed(
            "🎨 Tags de colores",
            "\n".join(lines) + "\n\nComprá con `/tags comprar`. Una vez comprado es tuyo: cambiás de color gratis con `/tags usar`.",
        )
        await interaction.response.send_message(embed=embed)

    @tags.command(name="comprar", description="Comprá un tag de color (te llega como rol)")
    @app_commands.choices(color=CHOICES)
    async def tags_buy(self, interaction: discord.Interaction, color: app_commands.Choice[str]):
        await interaction.response.defer()
        try:
            tag = await self.buy(interaction.guild, interaction.user, color.value)
        except TagError as e:
            return await interaction.followup.send(embed=error(e.message), ephemeral=True)
        await interaction.followup.send(
            embed=ok(f"Compraste el tag {tag.emoji} **{tag.name}** por **{fmt(tag.price)}** {COIN} y ya lo tenés puesto."),
        )

    @tags.command(name="usar", description="Ponete un tag que ya compraste")
    @app_commands.choices(color=CHOICES)
    async def tags_use(self, interaction: discord.Interaction, color: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        try:
            tag = await self.equip(interaction.guild, interaction.user, color.value)
        except TagError as e:
            return await interaction.followup.send(embed=error(e.message), ephemeral=True)
        await interaction.followup.send(embed=ok(f"Ahora llevás el tag {tag.emoji} **{tag.name}**."), ephemeral=True)

    @tags.command(name="quitar", description="Sacate el tag de color (seguís teniéndolo comprado)")
    async def tags_remove(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.unequip(interaction.user)
        except TagError as e:
            return await interaction.followup.send(embed=error(e.message), ephemeral=True)
        await interaction.followup.send(embed=ok("Te saqué el tag. Podés volver a ponértelo con `/tags usar`."), ephemeral=True)

    @tags.command(name="crear_roles", description="(Admin) Crea ahora los roles de todos los tags")
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.checks.has_permissions(manage_roles=True)
    async def tags_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            for t in TAGS:
                await self._role_for(interaction.guild, t, create=True)
        except TagError as e:
            return await interaction.followup.send(embed=error(e.message), ephemeral=True)
        await interaction.followup.send(embed=ok("Listo, los roles de los tags ya están creados."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tags(bot))
