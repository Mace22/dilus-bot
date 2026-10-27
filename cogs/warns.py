import datetime
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation import can_act_on
from utils.embeds import error, make_embed, ok

log = logging.getLogger("dilus-bot.warns")

WARN_LIMIT = 3          # al llegar a esta cantidad de warns se aplica un timeout automático
AUTO_TIMEOUT_MIN = 60   # duración de ese timeout (minutos)

RED, GREEN, ORANGE, BLUE = 0xEF4444, 0x22C55E, 0xF59E0B, 0x3B82F6


def clip(text: str | None, limit: int = 1000) -> str:
    text = text or "—"
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Warns(commands.Cog):
    """Sistema de advertencias + registro (logs) de lo que pasa en el servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        channel_id = await self.bot.db.get_setting(guild.id, "log_channel")
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel:
            try:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # Advertencias
    # ------------------------------------------------------------------
    @app_commands.command(name="warn", description="Advierte a un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, miembro: discord.Member, razon: app_commands.Range[str, 1, 300]):
        if miembro.bot:
            return await interaction.response.send_message(embed=error("No se puede advertir a un bot."), ephemeral=True)
        if msg := can_act_on(interaction, miembro):
            return await interaction.response.send_message(embed=error(msg), ephemeral=True)

        gid = interaction.guild_id
        await self.bot.db.execute(
            "INSERT INTO warns (guild_id, user_id, moderator_id, reason, created) VALUES (?, ?, ?, ?, ?)",
            (gid, miembro.id, interaction.user.id, razon, time.time()),
        )
        row = await self.bot.db.fetchone("SELECT COUNT(*) AS c FROM warns WHERE guild_id = ? AND user_id = ?", (gid, miembro.id))
        count = row["c"]

        text = f"⚠️ {miembro.mention} fue advertido ({count}/{WARN_LIMIT}).\n**Razón:** {razon}"
        if count >= WARN_LIMIT:
            try:
                await miembro.timeout(datetime.timedelta(minutes=AUTO_TIMEOUT_MIN), reason=f"{WARN_LIMIT} advertencias")
                text += f"\n🔇 Llegó al límite: timeout automático de {AUTO_TIMEOUT_MIN} minutos."
            except discord.HTTPException:
                text += "\n(No pude aplicarle el timeout automático: revisá mis permisos.)"

        await interaction.response.send_message(
            embed=make_embed(description=text, color=ORANGE), allowed_mentions=discord.AllowedMentions.none()
        )
        try:
            await miembro.send(f"⚠️ Recibiste una advertencia en **{interaction.guild.name}** ({count}/{WARN_LIMIT}).\nRazón: {razon}")
        except discord.HTTPException:
            pass

        embed = make_embed("⚠️ Advertencia", color=ORANGE)
        embed.add_field(name="Miembro", value=f"{miembro.mention} ({miembro})")
        embed.add_field(name="Moderador", value=interaction.user.mention)
        embed.add_field(name="Total", value=f"{count}/{WARN_LIMIT}")
        embed.add_field(name="Razón", value=clip(razon), inline=False)
        await self.send_log(interaction.guild, embed)

    @app_commands.command(name="warns", description="Mirá las advertencias de un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warns(self, interaction: discord.Interaction, miembro: discord.Member):
        rows = await self.bot.db.fetchall(
            "SELECT id, moderator_id, reason, created FROM warns WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 10",
            (interaction.guild_id, miembro.id),
        )
        if not rows:
            return await interaction.response.send_message(embed=ok(f"{miembro.display_name} no tiene advertencias."), ephemeral=True)
        lines = [
            f"`#{r['id']}` <t:{int(r['created'])}:d> por <@{r['moderator_id']}> — {clip(r['reason'], 120)}" for r in rows
        ]
        await interaction.response.send_message(
            embed=make_embed(f"⚠️ Advertencias de {miembro.display_name}", "\n".join(lines), color=ORANGE),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="unwarn", description="Borra una advertencia por su número (ver /warns)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unwarn(self, interaction: discord.Interaction, numero: int):
        cur = await self.bot.db.execute("DELETE FROM warns WHERE id = ? AND guild_id = ?", (numero, interaction.guild_id))
        if cur.rowcount == 0:
            return await interaction.response.send_message(embed=error("No encontré esa advertencia."), ephemeral=True)
        await interaction.response.send_message(embed=ok(f"Advertencia #{numero} eliminada."))

    @app_commands.command(name="clearwarns", description="Borra todas las advertencias de un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def clearwarns(self, interaction: discord.Interaction, miembro: discord.Member):
        cur = await self.bot.db.execute("DELETE FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild_id, miembro.id))
        await interaction.response.send_message(
            embed=ok(f"Se borraron {cur.rowcount} advertencia(s) de {miembro.mention}."),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ------------------------------------------------------------------
    # Logs automáticos (se envían al canal que se configura con /config logs)
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not message.content and not message.attachments:
            return
        embed = make_embed("🗑️ Mensaje borrado", color=RED)
        embed.add_field(name="Autor", value=f"{message.author.mention} ({message.author})")
        embed.add_field(name="Canal", value=message.channel.mention)
        embed.add_field(name="Contenido", value=clip(message.content), inline=False)
        if message.attachments:
            embed.add_field(name="Adjuntos", value=str(len(message.attachments)))
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = make_embed("✏️ Mensaje editado", color=BLUE)
        embed.add_field(name="Autor", value=f"{before.author.mention} ({before.author})")
        embed.add_field(name="Canal", value=f"{before.channel.mention} [ir al mensaje]({after.jump_url})")
        embed.add_field(name="Antes", value=clip(before.content), inline=False)
        embed.add_field(name="Después", value=clip(after.content), inline=False)
        await self.send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = make_embed("📥 Miembro nuevo", f"{member.mention} ({member})", color=GREEN)
        embed.add_field(name="Cuenta creada", value=discord.utils.format_dt(member.created_at, "R"))
        if (discord.utils.utcnow() - member.created_at).days < 7:
            embed.add_field(name="⚠️ Ojo", value="Cuenta de menos de 7 días", inline=False)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = make_embed("📤 Miembro se fue", f"{member.mention} ({member})", color=RED)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self.send_log(guild, make_embed("🔨 Baneo", f"{user.mention} ({user})", color=RED))

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await self.send_log(guild, make_embed("♻️ Desbaneo", f"{user.mention} ({user})", color=GREEN))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until and after.timed_out_until > discord.utils.utcnow():
                embed = make_embed("🔇 Timeout aplicado", f"{after.mention} hasta {discord.utils.format_dt(after.timed_out_until, 'f')}", color=ORANGE)
            else:
                embed = make_embed("🔊 Timeout quitado", after.mention, color=GREEN)
            await self.send_log(after.guild, embed)

        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            embed = make_embed("🏷️ Roles actualizados", f"{after.mention} ({after})", color=BLUE)
            if added:
                embed.add_field(name="Agregados", value=", ".join(r.mention for r in added))
            if removed:
                embed.add_field(name="Quitados", value=", ".join(r.mention for r in removed))
            await self.send_log(after.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Warns(bot))
