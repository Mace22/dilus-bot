"""Avisa quién entra al servidor y deja que el staff le dé el rol Crew reaccionando con ✅."""
import logging
import time

import discord
from discord.ext import commands

from utils import adminlog
from utils.crew import CHECK, NOTICE_KEEP_DAYS, is_staff, role_problem
from utils.embeds import make_embed

log = logging.getLogger("dilus-bot.crew")

GREEN = 0x22C55E


class Crew(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _say(self, channel, text: str, user: discord.abc.Snowflake | None = None):
        """Aviso corto que se borra solo (para no llenar el canal)."""
        try:
            await channel.send(text, delete_after=15, allowed_mentions=discord.AllowedMentions(users=[user] if user else False))
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Aviso de ingreso
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        db, guild = self.bot.db, member.guild
        channel_id = await db.get_setting(guild.id, "crew_channel")
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        role_id = await db.get_setting(guild.id, "crew_role")
        role = guild.get_role(role_id) if role_id else None

        embed = make_embed("📥 Nuevo ingreso", f"{member.mention} ({member})")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Cuenta creada", value=discord.utils.format_dt(member.created_at, "R"))
        embed.add_field(name="Miembro", value=f"#{guild.member_count}")
        if (discord.utils.utcnow() - member.created_at).days < 7:
            embed.add_field(name="⚠️ Ojo", value="Cuenta de menos de 7 días", inline=False)
        if role:
            embed.set_footer(text=f"Staff: reaccioná con {CHECK} para darle el rol {role.name}")
        try:
            msg = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning("No pude avisar el ingreso de %s en %s", member, guild.name)
            return
        await db.execute(
            "INSERT OR REPLACE INTO join_notices (message_id, guild_id, channel_id, user_id, granted_by, ts) VALUES (?, ?, ?, ?, NULL, ?)",
            (msg.id, guild.id, channel.id, member.id, time.time()),
        )
        await db.execute("DELETE FROM join_notices WHERE ts < ?", (time.time() - NOTICE_KEEP_DAYS * 86400,))
        if role:
            try:
                await msg.add_reaction(CHECK)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # Reacción del staff
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or str(payload.emoji) != CHECK or payload.user_id == self.bot.user.id:
            return
        db = self.bot.db
        row = await db.fetchone("SELECT * FROM join_notices WHERE message_id = ? AND guild_id = ?", (payload.message_id, payload.guild_id))
        if row is None or row["granted_by"] is not None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id) if guild else None
        reactor = payload.member
        if guild is None or channel is None or reactor is None or reactor.bot:
            return

        staff_role_id = await db.get_setting(guild.id, "crew_staff_role")
        if not is_staff(reactor, staff_role_id):
            try:  # no es staff: se saca su reacción para que no parezca que hizo algo
                await channel.get_partial_message(payload.message_id).remove_reaction(payload.emoji, reactor)
            except discord.HTTPException:
                pass
            return

        role_id = await db.get_setting(guild.id, "crew_role")
        role = guild.get_role(role_id) if role_id else None
        if role is None:
            return await self._say(channel, f"{reactor.mention} no hay un rol Crew configurado (`/config crew`).", reactor)
        if problem := role_problem(guild, role):
            return await self._say(channel, f"{reactor.mention} {problem}", reactor)

        target = guild.get_member(row["user_id"])
        if target is None:
            try:
                target = await guild.fetch_member(row["user_id"])
            except discord.HTTPException:
                return await self._say(channel, f"{reactor.mention} esa persona ya no está en el servidor.", reactor)

        # se "reclama" primero para que dos staff reaccionando a la vez no lo den dos veces
        cur = await db.execute("UPDATE join_notices SET granted_by = ? WHERE message_id = ? AND granted_by IS NULL", (reactor.id, payload.message_id))
        if cur.rowcount == 0:
            return
        already = role in target.roles
        if not already:
            try:
                await target.add_roles(role, reason=f"Rol Crew dado por {reactor} (reacción)")
            except discord.HTTPException:
                await db.execute("UPDATE join_notices SET granted_by = NULL WHERE message_id = ?", (payload.message_id,))
                return await self._say(channel, f"{reactor.mention} no pude darle el rol {role.name}. Revisá que mi rol esté por encima.", reactor)

        try:
            message = await channel.fetch_message(payload.message_id)
            embed = message.embeds[0].copy() if message.embeds else make_embed("📥 Nuevo ingreso", target.mention)
            embed.color = GREEN
            embed.add_field(name=f"{CHECK} Rol {role.name}", value=f"{'Ya lo tenía · ' if already else ''}confirmado por {reactor.mention}", inline=False)
            embed.set_footer(text="Listo")
            await message.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
        if not already:
            await adminlog.record(self.bot, guild, actor=reactor, action="crew_grant", target=target, detail=f"Rol {role.name} (reacción)", source="discord")


async def setup(bot: commands.Bot):
    await bot.add_cog(Crew(bot))
