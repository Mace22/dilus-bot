import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import BRAND_NAME, error, make_embed

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ayuda", description="Lista de comandos de Dilu's Bot")
    async def ayuda(self, interaction: discord.Interaction):
        embed = make_embed(f"✨ {BRAND_NAME}", "Estos son mis comandos:")
        embed.add_field(
            name="📈 Niveles",
            value="`/rank` `/top` `/horas` `/recompensas`\nAdmin: `/xp dar|reset` `/levelrole agregar|quitar`",
            inline=False,
        )
        embed.add_field(
            name="🤖 IA (Gemini)",
            value="`/ask` preguntá lo que quieras (o mencioname: @Dilu's Bot)\n`/olvidar` reinicia la charla • `/traducir`",
            inline=False,
        )
        embed.add_field(name="💘 Diversión", value="`/match` compatibilidad entre dos personas • `/encuesta`", inline=False)
        embed.add_field(
            name="🪙 Economía",
            value="`/balance` `/daily` `/trabajar` `/pay` `/ricos`\n`/apostar` `/slots` `/blackjack` • `/tienda` `/comprar`\nAdmin: `/economia dar|tienda_agregar|tienda_quitar`",
            inline=False,
        )
        embed.add_field(
            name="🎙️ Voz",
            value="`/entrar` entro a tu canal, silenciado • `/salir`\nCanales temporales: `/config tempvoice`",
            inline=False,
        )
        embed.add_field(name="🎁 Comunidad", value="`/sorteo crear|terminar` • `/ticket panel`", inline=False)
        embed.add_field(
            name="🛡️ Moderación",
            value="`/clear` `/kick` `/ban` `/timeout` `/untimeout`\n`/warn` `/warns` `/unwarn` `/clearwarns`",
            inline=False,
        )
        embed.add_field(
            name="⚙️ Configuración",
            value="`/config bienvenida|despedida|levelup|autorole|logs|tempvoice|ver`",
            inline=False,
        )
        embed.add_field(name="🔧 Otros", value="`/ping` `/avatar` `/serverinfo`\nAdmin: `/diagnostico` (revisa por qué la gente no puede usar el bot)", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="diagnostico", description="Revisa por qué la gente no puede usar los comandos del bot")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnostico(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, channel = interaction.guild, interaction.channel
        everyone = channel.permissions_for(guild.default_role)
        mine = channel.permissions_for(guild.me)

        def mark(flag: bool) -> str:
            return "✅" if flag else "❌"

        perms_lines = [
            f"{mark(everyone.view_channel)} @everyone puede ver este canal",
            f"{mark(everyone.use_application_commands)} @everyone tiene «Usar comandos de aplicaciones» acá",
            f"{mark(mine.send_messages)} El bot puede enviar mensajes",
            f"{mark(mine.embed_links)} El bot puede insertar enlaces (embeds)",
            f"{mark(mine.attach_files)} El bot puede adjuntar archivos (imágenes de /rank, /match, /blackjack)",
        ]

        # Restricciones puestas desde Ajustes del servidor > Integraciones, solo en comandos que son para todos
        blocked: list[str] = []
        problem = None
        try:
            commands_list = await self.bot.tree.fetch_commands()
            public = [c for c in commands_list if c.default_member_permissions is None]
            for cmd in public:
                try:
                    cmd_perms = await cmd.fetch_permissions(guild)
                except discord.NotFound:
                    continue  # sin restricciones
                for p in cmd_perms.permissions:
                    if p.permission is False:
                        target = "@everyone" if p.id == guild.id else f"<@&{p.id}>" if p.type == discord.AppCommandPermissionType.role else f"`{p.id}`"
                        blocked.append(f"`/{cmd.name}` bloqueado para {target}")
        except discord.HTTPException:
            problem = "No pude leer las restricciones de Integraciones. Revisalas a mano (ver abajo)."

        embed = make_embed("🔎 Diagnóstico")
        embed.add_field(name="Permisos en este canal", value="\n".join(perms_lines), inline=False)
        if problem:
            embed.add_field(name="Restricciones en Integraciones", value=problem, inline=False)
        elif blocked:
            shown = "\n".join(blocked[:12]) + (f"\n…y {len(blocked) - 12} más" if len(blocked) > 12 else "")
            embed.add_field(name="Restricciones en Integraciones", value=shown, inline=False)
        else:
            embed.add_field(name="Restricciones en Integraciones", value="✅ No encontré comandos públicos bloqueados.", inline=False)

        fixes = []
        if not everyone.view_channel or not everyone.use_application_commands:
            fixes.append("• En este canal (o su categoría): **Permisos → @everyone → activar «Usar comandos de aplicaciones»** (y «Ver canal»).")
        if blocked:
            fixes.append("• **Ajustes del servidor → Integraciones → Dilu's Bot**: abrí cada comando marcado y dejalo en «@everyone» (o usá «Restablecer»).")
        if not (mine.send_messages and mine.embed_links and mine.attach_files):
            fixes.append("• Dale al bot los permisos que marqué con ❌ en este canal.")
        if not fixes:
            fixes.append("• Todo se ve bien acá. Si alguien sigue sin poder, probá `/diagnostico` en el canal donde falla: los permisos cambian de canal en canal.")
        embed.add_field(name="Qué hacer", value="\n".join(fixes), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Latencia del bot")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! `{round(self.bot.latency * 1000)}ms`")

    @app_commands.command(name="avatar", description="Muestra el avatar de alguien")
    async def avatar(self, interaction: discord.Interaction, miembro: discord.User | None = None):
        user = miembro or interaction.user
        embed = make_embed(f"Avatar de {user.display_name}")
        embed.set_image(url=user.display_avatar.replace(size=1024).url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Información del servidor")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        embed = make_embed(f"📋 {g.name}")
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Dueño", value=f"<@{g.owner_id}>")
        embed.add_field(name="Miembros", value=str(g.member_count))
        embed.add_field(name="Canales", value=f"{len(g.text_channels)} texto / {len(g.voice_channels)} voz")
        embed.add_field(name="Roles", value=str(len(g.roles)))
        embed.add_field(name="Creado", value=discord.utils.format_dt(g.created_at, "D"))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="encuesta", description="Crea una encuesta con reacciones")
    @app_commands.describe(pregunta="La pregunta", opcion1="Opción 1", opcion2="Opción 2")
    @app_commands.guild_only()
    async def encuesta(
        self,
        interaction: discord.Interaction,
        pregunta: app_commands.Range[str, 1, 200],
        opcion1: app_commands.Range[str, 1, 100],
        opcion2: app_commands.Range[str, 1, 100],
        opcion3: app_commands.Range[str, 1, 100] | None = None,
        opcion4: app_commands.Range[str, 1, 100] | None = None,
        opcion5: app_commands.Range[str, 1, 100] | None = None,
    ):
        options = [o for o in (opcion1, opcion2, opcion3, opcion4, opcion5) if o]
        text = "\n".join(f"{NUMBER_EMOJIS[i]} {o}" for i, o in enumerate(options))
        embed = make_embed(f"📊 {pregunta}", text)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        for i in range(len(options)):
            try:
                await msg.add_reaction(NUMBER_EMOJIS[i])
            except discord.HTTPException:
                return await interaction.followup.send(
                    embed=error("No pude agregar las reacciones (me falta permiso)."), ephemeral=True
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
