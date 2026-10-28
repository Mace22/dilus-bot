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
            value="`/rank` `/top` `/horas`\nAdmin: `/xp dar|reset` `/levelrole agregar|quitar|lista`",
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
        embed.add_field(name="🔧 Otros", value="`/ping` `/avatar` `/serverinfo`", inline=False)
        await interaction.response.send_message(embed=embed)

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
