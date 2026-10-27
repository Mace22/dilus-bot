import asyncio
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import error, make_embed, ok

log = logging.getLogger("dilus-bot.tickets")


def ticket_owner_id(channel: discord.abc.GuildChannel) -> int | None:
    """El dueño del ticket se guarda en el topic del canal: 'ticket:<id>'."""
    topic = getattr(channel, "topic", None) or ""
    m = re.match(r"ticket:(\d+)", topic)
    return int(m.group(1)) if m else None


class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cerrar ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="dilu:ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        owner_id = ticket_owner_id(channel)
        if owner_id is None:
            return await interaction.response.send_message("Este canal no es un ticket.", ephemeral=True)

        staff_role_id = await interaction.client.db.get_setting(interaction.guild_id, "ticket_staff_role")
        is_staff = bool(staff_role_id) and any(r.id == staff_role_id for r in interaction.user.roles)
        if not (interaction.user.id == owner_id or is_staff or interaction.user.guild_permissions.manage_channels):
            return await interaction.response.send_message("No podés cerrar este ticket.", ephemeral=True)

        await interaction.response.send_message("🔒 Cerrando el ticket en 5 segundos...")
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket cerrado por {interaction.user}")
        except discord.HTTPException:
            pass


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="dilu:ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        db = interaction.client.db

        # Un solo ticket por persona
        for ch in guild.text_channels:
            if ticket_owner_id(ch) == user.id:
                return await interaction.response.send_message(
                    f"Ya tenés un ticket abierto: {ch.mention}", ephemeral=True
                )

        category_id = await db.get_setting(guild.id, "ticket_category")
        staff_role_id = await db.get_setting(guild.id, "ticket_staff_role")
        category = guild.get_channel(category_id) if category_id else None
        staff_role = guild.get_role(staff_role_id) if staff_role_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        safe_name = re.sub(r"[^a-z0-9-]", "", user.name.lower())[:20] or "usuario"
        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{safe_name}",
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                topic=f"ticket:{user.id}",
                reason=f"Ticket de {user}",
            )
        except discord.HTTPException:
            log.exception("No pude crear el ticket")
            return await interaction.response.send_message(
                embed=error("No pude crear el ticket. Revisá que tenga permiso de gestionar canales."), ephemeral=True
            )

        embed = make_embed(
            "🎫 Ticket abierto",
            f"Hola {user.mention}, contanos en qué podemos ayudarte.\n"
            f"{staff_role.mention + ' te va a atender pronto.' if staff_role else 'El staff te va a atender pronto.'}",
        )
        await channel.send(
            content=f"{user.mention} {staff_role.mention if staff_role else ''}".strip(),
            embed=embed,
            view=TicketControls(),
        )
        await interaction.response.send_message(f"Listo, tu ticket: {channel.mention}", ephemeral=True)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Registrar las vistas persistentes (los botones siguen andando tras reiniciar el bot)
        self.bot.add_view(TicketPanel())
        self.bot.add_view(TicketControls())

    ticket = app_commands.Group(
        name="ticket",
        description="Sistema de tickets de soporte",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @ticket.command(name="panel", description="Publica el panel para abrir tickets en este canal")
    @app_commands.describe(
        categoria="Categoría donde se crean los tickets (opcional)",
        staff="Rol que podrá ver y atender los tickets (opcional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def panel(
        self,
        interaction: discord.Interaction,
        categoria: discord.CategoryChannel | None = None,
        staff: discord.Role | None = None,
    ):
        await self.bot.db.set_setting(interaction.guild_id, "ticket_category", categoria.id if categoria else None)
        await self.bot.db.set_setting(interaction.guild_id, "ticket_staff_role", staff.id if staff else None)
        embed = make_embed("🎫 Soporte", "¿Necesitás ayuda? Tocá el botón de abajo y abrimos un canal privado para vos.")
        await interaction.channel.send(embed=embed, view=TicketPanel())
        await interaction.response.send_message(embed=ok("Panel publicado."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
