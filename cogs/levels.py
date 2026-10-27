import asyncio
import io
import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont

from utils.embeds import error, make_embed, ok

# ---------- Configuración (tocá estos valores a gusto) ----------
MESSAGE_XP = (15, 25)        # XP aleatoria por mensaje (mín, máx)
MESSAGE_COOLDOWN = 60        # segundos entre mensajes que dan XP
VOICE_XP_PER_MINUTE = 10     # XP por minuto en canal de voz
VOICE_MIN_HUMANS = 2         # personas (no bots) necesarias en el canal para sumar XP de voz
# -----------------------------------------------------------------


def xp_needed(level: int) -> int:
    """XP necesaria para pasar de `level` a `level + 1`."""
    return 5 * level**2 + 50 * level + 100


def level_from_xp(total_xp: int) -> tuple[int, int, int]:
    """Devuelve (nivel, xp dentro del nivel, xp necesaria para el siguiente)."""
    level = 0
    remaining = total_xp
    while remaining >= xp_needed(level):
        remaining -= xp_needed(level)
        level += 1
    return level, remaining, xp_needed(level)


def format_hours(seconds: int) -> str:
    hours, rem = divmod(int(seconds), 3600)
    minutes = rem // 60
    return f"{hours}h {minutes}m"


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow muy viejo
        return ImageFont.load_default()


def render_card(avatar_bytes: bytes | None, name: str, level: int, xp: int, needed: int, rank: int, total_xp: int) -> io.BytesIO:
    width, height = 800, 240
    img = Image.new("RGB", (width, height), (20, 20, 32))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((10, 10, width - 10, height - 10), radius=26, fill=(32, 33, 52))
    draw.rounded_rectangle((10, 10, 24, height - 10), radius=6, fill=(139, 92, 246))

    if avatar_bytes:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB").resize((150, 150))
        mask = Image.new("L", (150, 150), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 150, 150), fill=255)
        img.paste(avatar, (45, 45), mask)

    big, mid, small = _font(40), _font(28), _font(20)
    draw.text((225, 40), name[:22], font=big, fill=(255, 255, 255))
    draw.text((width - 40, 45), f"Nivel {level}", font=mid, fill=(167, 139, 250), anchor="ra")
    draw.text((width - 40, 85), f"Rank #{rank}", font=small, fill=(180, 180, 200), anchor="ra")
    draw.text((225, 105), f"{total_xp:,} XP totales".replace(",", "."), font=small, fill=(180, 180, 200))

    bar_x1, bar_y1, bar_x2, bar_y2 = 225, 160, width - 40, 192
    draw.rounded_rectangle((bar_x1, bar_y1, bar_x2, bar_y2), radius=16, fill=(55, 56, 80))
    ratio = max(0.0, min(1.0, xp / needed)) if needed else 0
    if ratio > 0:
        fill_x2 = max(bar_x1 + 20, bar_x1 + int((bar_x2 - bar_x1) * ratio))
        draw.rounded_rectangle((bar_x1, bar_y1, fill_x2, bar_y2), radius=16, fill=(139, 92, 246))
    draw.text((bar_x2, bar_y1 - 8), f"{xp} / {needed} XP", font=small, fill=(220, 220, 235), anchor="rb")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldowns: dict[tuple[int, int], float] = {}

    async def cog_load(self):
        self.voice_xp_loop.start()

    async def cog_unload(self):
        self.voice_xp_loop.cancel()

    # ------------------------------------------------------------------
    # Núcleo
    # ------------------------------------------------------------------
    async def add_xp(self, guild_id: int, user_id: int, amount: int, *, messages: int = 0, voice_seconds: int = 0):
        """Suma XP y devuelve (nivel_anterior, nivel_nuevo)."""
        db = self.bot.db
        row = await db.fetchone("SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        old_xp = row["xp"] if row else 0
        new_xp = max(0, old_xp + amount)
        old_level = level_from_xp(old_xp)[0]
        new_level = level_from_xp(new_xp)[0]
        await db.execute(
            "INSERT INTO levels (guild_id, user_id, xp, level, messages, voice_seconds) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = excluded.xp, level = excluded.level, "
            "messages = messages + excluded.messages, voice_seconds = voice_seconds + excluded.voice_seconds",
            (guild_id, user_id, new_xp, new_level, messages, voice_seconds),
        )
        return old_level, new_level

    async def sync_level_roles(self, member: discord.Member, level: int):
        rows = await self.bot.db.fetchall(
            "SELECT role_id FROM level_roles WHERE guild_id = ? AND level <= ?", (member.guild.id, level)
        )
        to_add = []
        for r in rows:
            role = member.guild.get_role(r["role_id"])
            if role and role not in member.roles and role < member.guild.me.top_role:
                to_add.append(role)
        if to_add:
            try:
                await member.add_roles(*to_add, reason="Recompensa de nivel - Dilu's Bot")
            except discord.HTTPException:
                pass

    async def handle_level_up(self, member: discord.Member, new_level: int, fallback: discord.abc.Messageable | None):
        await self.sync_level_roles(member, new_level)
        channel_id = await self.bot.db.get_setting(member.guild.id, "levelup_channel")
        channel = member.guild.get_channel(channel_id) if channel_id else fallback
        if channel:
            try:
                await channel.send(f"🎉 {member.mention} subió al **nivel {new_level}**!")
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # XP por mensajes
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return
        key = (message.guild.id, message.author.id)
        now = time.time()
        if now - self._cooldowns.get(key, 0) < MESSAGE_COOLDOWN:
            return
        self._cooldowns[key] = now

        old, new = await self.add_xp(message.guild.id, message.author.id, random.randint(*MESSAGE_XP), messages=1)
        if new > old:
            await self.handle_level_up(message.author, new, message.channel)

    # ------------------------------------------------------------------
    # XP por voz
    # ------------------------------------------------------------------
    @tasks.loop(seconds=60)
    async def voice_xp_loop(self):
        for guild in self.bot.guilds:
            for vc in guild.voice_channels + list(guild.stage_channels):
                if guild.afk_channel and vc.id == guild.afk_channel.id:
                    continue
                humans = [m for m in vc.members if not m.bot]
                if len(humans) < VOICE_MIN_HUMANS:
                    continue
                for m in humans:
                    if not m.voice or m.voice.deaf or m.voice.self_deaf:
                        continue
                    old, new = await self.add_xp(
                        guild.id, m.id, VOICE_XP_PER_MINUTE, voice_seconds=60
                    )
                    if new > old:
                        await self.handle_level_up(m, new, None)

    @voice_xp_loop.before_loop
    async def _before_voice_loop(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------
    @app_commands.command(name="rank", description="Mirá tu nivel y XP (o el de otra persona)")
    @app_commands.describe(miembro="Persona a consultar (por defecto, vos)")
    @app_commands.guild_only()
    async def rank(self, interaction: discord.Interaction, miembro: discord.Member | None = None):
        member = miembro or interaction.user
        if member.bot:
            return await interaction.response.send_message(embed=error("Los bots no tienen nivel."), ephemeral=True)
        await interaction.response.defer()

        row = await self.bot.db.fetchone(
            "SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?", (interaction.guild_id, member.id)
        )
        total_xp = row["xp"] if row else 0
        level, xp, needed = level_from_xp(total_xp)
        pos = await self.bot.db.fetchone(
            "SELECT COUNT(*) + 1 AS pos FROM levels WHERE guild_id = ? AND xp > ?", (interaction.guild_id, total_xp)
        )

        try:
            avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
        except discord.HTTPException:
            avatar_bytes = None

        buf = await asyncio.to_thread(
            render_card, avatar_bytes, member.display_name, level, xp, needed, pos["pos"], total_xp
        )
        await interaction.followup.send(file=discord.File(buf, filename="rank.png"))

    @app_commands.command(name="top", description="Ranking del servidor")
    @app_commands.describe(tipo="Ordenar por nivel/XP o por horas en voz")
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Nivel / XP", value="xp"),
            app_commands.Choice(name="Horas en voz", value="voz"),
        ]
    )
    @app_commands.guild_only()
    async def top(self, interaction: discord.Interaction, tipo: app_commands.Choice[str] | None = None):
        mode = tipo.value if tipo else "xp"
        column = "voice_seconds" if mode == "voz" else "xp"
        rows = await self.bot.db.fetchall(
            f"SELECT user_id, xp, voice_seconds FROM levels WHERE guild_id = ? AND {column} > 0 "
            f"ORDER BY {column} DESC LIMIT 10",
            (interaction.guild_id,),
        )
        if not rows:
            return await interaction.response.send_message(embed=error("Todavía no hay datos para el ranking."))

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, r in enumerate(rows):
            prefix = medals[i] if i < 3 else f"`{i + 1}.`"
            if mode == "voz":
                detail = format_hours(r["voice_seconds"])
            else:
                detail = f"Nivel {level_from_xp(r['xp'])[0]} • {r['xp']} XP"
            lines.append(f"{prefix} <@{r['user_id']}> — {detail}")

        title = "🎙️ Top horas en voz" if mode == "voz" else "🏆 Top niveles"
        await interaction.response.send_message(
            embed=make_embed(title, "\n".join(lines)), allowed_mentions=discord.AllowedMentions.none()
        )

    @app_commands.command(name="horas", description="Mirá cuántas horas pasaste en canales de voz")
    @app_commands.describe(miembro="Persona a consultar (por defecto, vos)")
    @app_commands.guild_only()
    async def horas(self, interaction: discord.Interaction, miembro: discord.Member | None = None):
        member = miembro or interaction.user
        row = await self.bot.db.fetchone(
            "SELECT voice_seconds, messages FROM levels WHERE guild_id = ? AND user_id = ?",
            (interaction.guild_id, member.id),
        )
        secs = row["voice_seconds"] if row else 0
        msgs = row["messages"] if row else 0
        embed = make_embed(f"📊 Actividad de {member.display_name}")
        embed.add_field(name="🎙️ Tiempo en voz", value=format_hours(secs))
        embed.add_field(name="💬 Mensajes con XP", value=str(msgs))
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ---- Administración de XP ----
    xp_group = app_commands.Group(
        name="xp",
        description="Administrar la XP de los miembros",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @xp_group.command(name="dar", description="Suma (o resta con número negativo) XP a un miembro")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def xp_dar(self, interaction: discord.Interaction, miembro: discord.Member, cantidad: int):
        old, new = await self.add_xp(interaction.guild_id, miembro.id, cantidad)
        await self.sync_level_roles(miembro, new)
        await interaction.response.send_message(
            embed=ok(f"{miembro.mention} ahora está en nivel **{new}** (cambio de XP: {cantidad:+d})."),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @xp_group.command(name="reset", description="Reinicia la XP de un miembro")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def xp_reset(self, interaction: discord.Interaction, miembro: discord.Member):
        await self.bot.db.execute(
            "DELETE FROM levels WHERE guild_id = ? AND user_id = ?", (interaction.guild_id, miembro.id)
        )
        await interaction.response.send_message(
            embed=ok(f"Se reinició la XP de {miembro.mention}."), allowed_mentions=discord.AllowedMentions.none()
        )

    # ---- Roles por nivel ----
    levelrole = app_commands.Group(
        name="levelrole",
        description="Roles que se dan al llegar a cierto nivel",
        guild_only=True,
        default_permissions=discord.Permissions(manage_roles=True),
    )

    @levelrole.command(name="agregar", description="Dar un rol al alcanzar un nivel")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def levelrole_add(self, interaction: discord.Interaction, nivel: app_commands.Range[int, 1, 500], rol: discord.Role):
        if rol >= interaction.guild.me.top_role or rol.is_default() or rol.managed:
            return await interaction.response.send_message(
                embed=error("No puedo asignar ese rol (está por encima del mío o es un rol especial)."), ephemeral=True
            )
        await self.bot.db.execute(
            "INSERT INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id",
            (interaction.guild_id, nivel, rol.id),
        )
        await interaction.response.send_message(
            embed=ok(f"Al llegar al nivel **{nivel}** se dará el rol {rol.mention}."),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @levelrole.command(name="quitar", description="Quitar la recompensa de un nivel")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def levelrole_remove(self, interaction: discord.Interaction, nivel: app_commands.Range[int, 1, 500]):
        await self.bot.db.execute(
            "DELETE FROM level_roles WHERE guild_id = ? AND level = ?", (interaction.guild_id, nivel)
        )
        await interaction.response.send_message(embed=ok(f"Se quitó la recompensa del nivel **{nivel}**."))

    @levelrole.command(name="lista", description="Ver las recompensas configuradas")
    async def levelrole_list(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level", (interaction.guild_id,)
        )
        if not rows:
            return await interaction.response.send_message(embed=error("No hay recompensas configuradas."), ephemeral=True)
        text = "\n".join(f"Nivel **{r['level']}** → <@&{r['role_id']}>" for r in rows)
        await interaction.response.send_message(
            embed=make_embed("🎁 Recompensas por nivel", text), allowed_mentions=discord.AllowedMentions.none()
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Levels(bot))
