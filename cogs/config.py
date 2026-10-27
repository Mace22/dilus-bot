import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import error, make_embed, ok

log = logging.getLogger("dilus-bot.config")


class Config(commands.Cog):
    """Bienvenida, despedida, autorole y ajustes generales."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        db = self.bot.db

        role_id = await db.get_setting(member.guild.id, "autorole")
        if role_id:
            role = member.guild.get_role(role_id)
            if role and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Autorole - Dilu's Bot")
                except discord.HTTPException:
                    log.warning("No pude dar el autorole en %s", member.guild.name)

        channel_id = await db.get_setting(member.guild.id, "welcome_channel")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if channel:
            embed = make_embed(
                f"¡Bienvenido/a a {member.guild.name}!",
                f"Hola {member.mention}, qué bueno tenerte acá 🎉\nSos el miembro **#{member.guild.member_count}**.",
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        channel_id = await self.bot.db.get_setting(member.guild.id, "goodbye_channel")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if channel:
            try:
                await channel.send(embed=make_embed(description=f"👋 **{member.display_name}** se fue del servidor."))
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # Comandos /config
    # ------------------------------------------------------------------
    config = app_commands.Group(
        name="config",
        description="Configurar Dilu's Bot en este servidor",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    async def _set_channel(self, interaction: discord.Interaction, key: str, channel: discord.TextChannel | None, label: str):
        if channel is not None:
            perms = channel.permissions_for(interaction.guild.me)
            if not (perms.view_channel and perms.send_messages):
                return await interaction.response.send_message(
                    embed=error(f"No tengo permiso para escribir en {channel.mention}."), ephemeral=True
                )
        await self.bot.db.set_setting(interaction.guild_id, key, channel.id if channel else None)
        if channel:
            await interaction.response.send_message(embed=ok(f"{label}: {channel.mention}"))
        else:
            await interaction.response.send_message(embed=ok(f"{label} desactivado."))

    @config.command(name="bienvenida", description="Canal de bienvenida (sin canal = desactivar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        await self._set_channel(interaction, "welcome_channel", canal, "Canal de bienvenida")

    @config.command(name="despedida", description="Canal de despedida (sin canal = desactivar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        await self._set_channel(interaction, "goodbye_channel", canal, "Canal de despedida")

    @config.command(name="levelup", description="Canal para avisos de subida de nivel (sin canal = en el mismo chat)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def levelup(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        await self._set_channel(interaction, "levelup_channel", canal, "Canal de level up")

    @config.command(name="autorole", description="Rol automático para nuevos miembros (sin rol = desactivar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autorole(self, interaction: discord.Interaction, rol: discord.Role | None = None):
        if rol is not None and (rol >= interaction.guild.me.top_role or rol.is_default() or rol.managed):
            return await interaction.response.send_message(
                embed=error("No puedo asignar ese rol (está por encima del mío o es un rol especial)."), ephemeral=True
            )
        await self.bot.db.set_setting(interaction.guild_id, "autorole", rol.id if rol else None)
        msg = f"Autorole: {rol.mention}" if rol else "Autorole desactivado."
        await interaction.response.send_message(embed=ok(msg), allowed_mentions=discord.AllowedMentions.none())

    @config.command(name="logs", description="Canal de logs: mensajes borrados/editados, bans, roles... (sin canal = desactivar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        await self._set_channel(interaction, "log_channel", canal, "Canal de logs")

    @config.command(name="tempvoice", description="Canal de voz 'lobby' que crea canales temporales (sin canal = desactivar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tempvoice(self, interaction: discord.Interaction, canal: discord.VoiceChannel | None = None):
        if canal is not None:
            perms = interaction.guild.me.guild_permissions
            if not (perms.manage_channels and perms.move_members):
                return await interaction.response.send_message(
                    embed=error("Necesito los permisos **Gestionar canales** y **Mover miembros**."), ephemeral=True
                )
        await self.bot.db.set_setting(interaction.guild_id, "tempvoice_channel", canal.id if canal else None)
        if canal:
            await interaction.response.send_message(
                embed=ok(f"Cuando alguien entre a {canal.mention} se le creará un canal de voz propio.")
            )
        else:
            await interaction.response.send_message(embed=ok("Canales temporales desactivados."))

    @config.command(name="ver", description="Ver la configuración actual")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view(self, interaction: discord.Interaction):
        db = self.bot.db
        gid = interaction.guild_id

        def ch(v):
            return f"<#{v}>" if v else "—"

        welcome = await db.get_setting(gid, "welcome_channel")
        goodbye = await db.get_setting(gid, "goodbye_channel")
        levelup = await db.get_setting(gid, "levelup_channel")
        autorole = await db.get_setting(gid, "autorole")
        logs = await db.get_setting(gid, "log_channel")
        tempvoice = await db.get_setting(gid, "tempvoice_channel")
        embed = make_embed("⚙️ Configuración")
        embed.add_field(name="Bienvenida", value=ch(welcome))
        embed.add_field(name="Despedida", value=ch(goodbye))
        embed.add_field(name="Level up", value=ch(levelup) if levelup else "mismo chat")
        embed.add_field(name="Autorole", value=f"<@&{autorole}>" if autorole else "—")
        embed.add_field(name="Logs", value=ch(logs))
        embed.add_field(name="Voz temporal (lobby)", value=ch(tempvoice))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))
