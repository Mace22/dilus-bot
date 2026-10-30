import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import BRAND_NAME, error, make_embed

NUMBER_EMOJIS = ["1ï¸âƒ£", "2ï¸âƒ£", "3ï¸âƒ£", "4ï¸âƒ£", "5ï¸âƒ£"]


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ayuda", description="Lista de comandos de Dilu's Bot")
    async def ayuda(self, interaction: discord.Interaction):
        embed = make_embed(f"âœ¨ {BRAND_NAME}", "Estos son mis comandos:")
        embed.add_field(
            name="ðŸ“ˆ Niveles",
            value="`/rank` `/top` `/horas` `/recompensas`\nAdmin: `/xp dar|reset` `/levelrole agregar|quitar`",
            inline=False,
        )
        embed.add_field(
            name="ðŸ¤– IA (Gemini)",
            value="`/ask` preguntÃ¡ lo que quieras (o mencioname: @Dilu's Bot)\n`/olvidar` reinicia la charla â€¢ `/traducir`",
            inline=False,
        )
        embed.add_field(name="ðŸ’˜ DiversiÃ³n", value="`/match` compatibilidad entre dos personas â€¢ `/encuesta`", inline=False)
        embed.add_field(
            name="ðŸª™ EconomÃ­a",
            value="`/balance` `/daily` `/trabajar` `/pay` `/ricos`\n`/apostar` `/slots` `/blackjack` `/ruleta` â€¢ `/tienda` `/comprar`\nAdmin: `/economia dar|tienda_agregar|tienda_quitar`",
            inline=False,
        )
        embed.add_field(
            name="ðŸŽ™ï¸ Voz",
            value="`/entrar` entro a tu canal, silenciado â€¢ `/salir`\nCanales temporales: `/config tempvoice`",
            inline=False,
        )
        embed.add_field(name="ðŸŒ Panel web", value="`/panel` tu economÃ­a, stats, ruleta y blackjack desde el navegador", inline=False)
        embed.add_field(name="ðŸŽ Comunidad", value="`/sorteo crear|terminar` â€¢ `/ticket panel`", inline=False)
        embed.add_field(
            name="ðŸ›¡ï¸ ModeraciÃ³n",
            value="`/clear` `/kick` `/ban` `/timeout` `/untimeout`\n`/warn` `/warns` `/unwarn` `/clearwarns`",
            inline=False,
        )
        embed.add_field(
            name="âš™ï¸ ConfiguraciÃ³n",
            value="`/config bienvenida|despedida|levelup|autorole|logs|tempvoice|ver`",
            inline=False,
        )
        embed.add_field(name="ðŸ”§ Otros", value="`/ping` `/avatar` `/serverinfo`\nAdmin: `/diagnostico` (revisa por quÃ© la gente no puede usar el bot)", inline=False)
        await interaction.response.send_message(embed=embed)

    @staticmethod
    def _describe_target(p: dict, guild: discord.Guild) -> str:
        """Convierte una regla de Integraciones (rol / miembro / canal) en texto legible."""
        pid, ptype = int(p["id"]), p.get("type")
        if ptype == 1:  # rol
            return "@everyone" if pid == guild.id else f"<@&{pid}>"
        if ptype == 2:  # miembro
            return f"<@{pid}>"
        if ptype == 3:  # canal
            return "todos los canales" if pid == guild.id - 1 else f"<#{pid}>"
        return f"`{pid}`"

    @app_commands.command(name="diagnostico", description="Revisa por quÃ© la gente no puede usar los comandos del bot")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnostico(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, channel = interaction.guild, interaction.channel
        everyone = channel.permissions_for(guild.default_role)
        mine = channel.permissions_for(guild.me)

        def mark(flag: bool) -> str:
            return "âœ…" if flag else "âŒ"

        perms_lines = [
            f"{mark(everyone.view_channel)} @everyone puede ver este canal",
            f"{mark(everyone.use_application_commands)} @everyone tiene Â«Usar comandos de aplicacionesÂ» acÃ¡",
            f"{mark(mine.send_messages)} El bot puede enviar mensajes",
            f"{mark(mine.embed_links)} El bot puede insertar enlaces (embeds)",
            f"{mark(mine.attach_files)} El bot puede adjuntar archivos (imÃ¡genes de /rank, /match, /blackjack)",
        ]

        # Restricciones de Ajustes del servidor > Integraciones (una sola consulta trae todo)
        app_wide: list[str] = []      # ajuste general del bot: afecta a TODOS los comandos
        app_blocks_everyone = False
        per_command: list[str] = []   # comandos pÃºblicos bloqueados uno por uno
        problem = None
        try:
            entries = await self.bot.http.get_guild_application_command_permissions(self.bot.application_id, guild.id)
            by_id = {c.id: c for c in await self.bot.tree.fetch_commands()}
            for entry in entries:
                cmd_id = int(entry["id"])
                rules = entry.get("permissions", [])
                if cmd_id == self.bot.application_id:
                    for r in rules:
                        who = self._describe_target(r, guild)
                        app_wide.append(f"{'âœ… permitido' if r['permission'] else 'â›” bloqueado'}: {who}")
                        if r["permission"] is False and int(r["id"]) in (guild.id, guild.id - 1):
                            app_blocks_everyone = True
                    continue
                cmd = by_id.get(cmd_id)
                if cmd is None or cmd.default_member_permissions is not None:
                    continue  # comando desconocido o de admin: no importa
                for r in rules:
                    if r["permission"] is False:
                        per_command.append(f"`/{cmd.name}` bloqueado para {self._describe_target(r, guild)}")
        except discord.HTTPException:
            problem = "No pude leer las restricciones de Integraciones. Revisalas a mano (ver abajo)."

        embed = make_embed("ðŸ”Ž DiagnÃ³stico")
        embed.add_field(name="Permisos en este canal", value="\n".join(perms_lines), inline=False)

        if problem:
            embed.add_field(name="Restricciones en Integraciones", value=problem, inline=False)
        else:
            parts = []
            if app_wide:
                parts.append("**Ajuste general del bot (afecta a TODOS los comandos):**\n" + "\n".join(app_wide[:10]))
            if per_command:
                shown = "\n".join(per_command[:10]) + (f"\nâ€¦y {len(per_command) - 10} mÃ¡s" if len(per_command) > 10 else "")
                parts.append("**Comandos bloqueados uno por uno:**\n" + shown)
            embed.add_field(
                name="Restricciones en Integraciones",
                value="\n\n".join(parts) if parts else "âœ… No encontrÃ© restricciones puestas desde Integraciones.",
                inline=False,
            )

        fixes = []
        if not everyone.view_channel or not everyone.use_application_commands:
            fixes.append("â€¢ En este canal (o su categorÃ­a): **Permisos â†’ @everyone â†’ activar Â«Usar comandos de aplicacionesÂ»** (y Â«Ver canalÂ»).")
        if app_blocks_everyone:
            fixes.append("â€¢ **Ajustes del servidor â†’ Integraciones â†’ Dilu's Bot**: en el ajuste general (arriba de la lista de comandos) dejÃ¡ a **@everyone** como permitido y Â«Todos los canalesÂ».")
        if per_command:
            fixes.append("â€¢ En esa misma pantalla, abrÃ­ cada comando marcado y dejalo en Â«@everyoneÂ» (o usÃ¡ Â«RestablecerÂ»).")
        if not (mine.send_messages and mine.embed_links and mine.attach_files):
            fixes.append("â€¢ Dale al bot los permisos que marquÃ© con âŒ en este canal.")
        if problem:
            fixes.append("â€¢ EntrÃ¡ a **Ajustes del servidor â†’ Integraciones â†’ Dilu's Bot** y revisÃ¡ que **@everyone** estÃ© permitido y los comandos no tengan restricciones.")
        if not fixes:
            fixes.append("â€¢ Todo se ve bien acÃ¡. Si alguien sigue sin poder, ejecutÃ¡ `/diagnostico` en el canal donde falla: los permisos cambian de canal en canal.")
        embed.add_field(name="QuÃ© hacer", value="\n".join(fixes), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Latencia del bot")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"ðŸ“ Pong! `{round(self.bot.latency * 1000)}ms`")

    @app_commands.command(name="avatar", description="Muestra el avatar de alguien")
    async def avatar(self, interaction: discord.Interaction, miembro: discord.User | None = None):
        user = miembro or interaction.user
        embed = make_embed(f"Avatar de {user.display_name}")
        embed.set_image(url=user.display_avatar.replace(size=1024).url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="InformaciÃ³n del servidor")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        embed = make_embed(f"ðŸ“‹ {g.name}")
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="DueÃ±o", value=f"<@{g.owner_id}>")
        embed.add_field(name="Miembros", value=str(g.member_count))
        embed.add_field(name="Canales", value=f"{len(g.text_channels)} texto / {len(g.voice_channels)} voz")
        embed.add_field(name="Roles", value=str(len(g.roles)))
        embed.add_field(name="Creado", value=discord.utils.format_dt(g.created_at, "D"))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="encuesta", description="Crea una encuesta con reacciones")
    @app_commands.describe(pregunta="La pregunta", opcion1="OpciÃ³n 1", opcion2="OpciÃ³n 2")
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
        embed = make_embed(f"ðŸ“Š {pregunta}", text)
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
