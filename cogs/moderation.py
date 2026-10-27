import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import error, ok


def can_act_on(interaction: discord.Interaction, target: discord.Member) -> str | None:
    """Devuelve un mensaje de error si NO se puede actuar sobre `target`, o None si está todo bien."""
    guild = interaction.guild
    if target.id == interaction.user.id:
        return "No podés hacerte eso a vos mismo."
    if target.id == guild.owner_id:
        return "No se puede actuar sobre el dueño del servidor."
    if target.id == interaction.client.user.id:
        return "Eso no, che."
    if interaction.user.id != guild.owner_id and target.top_role >= interaction.user.top_role:
        return "Esa persona tiene un rol igual o superior al tuyo."
    if target.top_role >= guild.me.top_role:
        return "Esa persona tiene un rol igual o superior al mío."
    return None


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="clear", description="Borra mensajes del canal")
    @app_commands.describe(cantidad="Cuántos mensajes borrar (1-100)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, cantidad: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=cantidad)
        await interaction.followup.send(embed=ok(f"Borré {len(deleted)} mensaje(s)."), ephemeral=True)

    @app_commands.command(name="kick", description="Expulsa a un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, miembro: discord.Member, razon: str | None = None):
        if msg := can_act_on(interaction, miembro):
            return await interaction.response.send_message(embed=error(msg), ephemeral=True)
        await miembro.kick(reason=f"{interaction.user} — {razon or 'Sin razón'}")
        await interaction.response.send_message(
            embed=ok(f"**{miembro}** fue expulsado. Razón: {razon or 'Sin razón'}")
        )

    @app_commands.command(name="ban", description="Banea a un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, miembro: discord.Member, razon: str | None = None):
        if msg := can_act_on(interaction, miembro):
            return await interaction.response.send_message(embed=error(msg), ephemeral=True)
        await miembro.ban(reason=f"{interaction.user} — {razon or 'Sin razón'}", delete_message_days=0)
        await interaction.response.send_message(
            embed=ok(f"**{miembro}** fue baneado. Razón: {razon or 'Sin razón'}")
        )

    @app_commands.command(name="timeout", description="Silencia temporalmente a un miembro")
    @app_commands.describe(minutos="Duración en minutos (máx. 40320 = 28 días)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        miembro: discord.Member,
        minutos: app_commands.Range[int, 1, 40320],
        razon: str | None = None,
    ):
        if msg := can_act_on(interaction, miembro):
            return await interaction.response.send_message(embed=error(msg), ephemeral=True)
        await miembro.timeout(datetime.timedelta(minutes=minutos), reason=f"{interaction.user} — {razon or 'Sin razón'}")
        await interaction.response.send_message(
            embed=ok(f"**{miembro}** quedó en timeout por {minutos} minuto(s). Razón: {razon or 'Sin razón'}")
        )

    @app_commands.command(name="untimeout", description="Quita el timeout a un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, miembro: discord.Member):
        await miembro.timeout(None, reason=f"{interaction.user}")
        await interaction.response.send_message(embed=ok(f"Se quitó el timeout a **{miembro}**."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
