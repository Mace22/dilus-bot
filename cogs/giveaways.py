import logging
import random
import re
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.embeds import BRAND_COLOR, error, make_embed, ok

log = logging.getLogger("dilus-bot.giveaways")

DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$", re.IGNORECASE)
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(text: str) -> int | None:
    """'30m' -> 1800, '2h' -> 7200, '1d' -> 86400."""
    m = DURATION_RE.match(text.strip())
    if not m:
        return None
    return int(m.group(1)) * UNITS[m.group(2).lower()]


class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Participar", style=discord.ButtonStyle.success, emoji="🎉", custom_id="dilu:giveaway:join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = interaction.client.db
        mid = interaction.message.id
        row = await db.fetchone("SELECT ended FROM giveaways WHERE message_id = ?", (mid,))
        if not row or row["ended"]:
            return await interaction.response.send_message("Este sorteo ya terminó.", ephemeral=True)

        exists = await db.fetchone(
            "SELECT 1 FROM giveaway_entries WHERE message_id = ? AND user_id = ?", (mid, interaction.user.id)
        )
        if exists:
            await db.execute("DELETE FROM giveaway_entries WHERE message_id = ? AND user_id = ?", (mid, interaction.user.id))
            msg = "Saliste del sorteo."
        else:
            await db.execute("INSERT INTO giveaway_entries (message_id, user_id) VALUES (?, ?)", (mid, interaction.user.id))
            msg = "¡Estás participando! Suerte 🍀 (tocá de nuevo para salir)."
        count = await db.fetchone("SELECT COUNT(*) AS c FROM giveaway_entries WHERE message_id = ?", (mid,))
        await interaction.response.send_message(f"{msg} Participantes: **{count['c']}**", ephemeral=True)


class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(GiveawayView())
        self.check_giveaways.start()

    async def cog_unload(self):
        self.check_giveaways.cancel()

    # ------------------------------------------------------------------
    async def finish(self, message_id: int):
        db = self.bot.db
        g = await db.fetchone("SELECT * FROM giveaways WHERE message_id = ? AND ended = 0", (message_id,))
        if not g:
            return False
        await db.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,))

        guild = self.bot.get_guild(g["guild_id"])
        channel = guild.get_channel(g["channel_id"]) if guild else None
        if not channel:
            return True

        entries = await db.fetchall("SELECT user_id FROM giveaway_entries WHERE message_id = ?", (message_id,))
        pool = [e["user_id"] for e in entries if guild.get_member(e["user_id"])]
        winners = random.sample(pool, min(g["winners"], len(pool))) if pool else []

        try:
            message = await channel.fetch_message(message_id)
        except discord.HTTPException:
            message = None

        if winners:
            mentions = ", ".join(f"<@{w}>" for w in winners)
            result = f"🏆 Ganador(es): {mentions}"
        else:
            result = "😕 Nadie participó."

        if message:
            embed = make_embed(f"🎁 {g['prize']}", f"**Sorteo finalizado**\n{result}\nOrganizó: <@{g['host_id']}>", color=0x6B7280)
            try:
                await message.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass
        try:
            await channel.send(
                f"🎉 Terminó el sorteo de **{g['prize']}**\n{result}",
                reference=message if message else None,
            )
        except discord.HTTPException:
            pass
        return True

    @tasks.loop(seconds=15)
    async def check_giveaways(self):
        rows = await self.bot.db.fetchall(
            "SELECT message_id FROM giveaways WHERE ended = 0 AND end_time <= ?", (time.time(),)
        )
        for r in rows:
            try:
                await self.finish(r["message_id"])
            except Exception:
                log.exception("Error al finalizar sorteo %s", r["message_id"])

    @check_giveaways.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    sorteo = app_commands.Group(
        name="sorteo",
        description="Sorteos con botón",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @sorteo.command(name="crear", description="Crea un sorteo")
    @app_commands.describe(
        premio="Qué se sortea",
        duracion="Ej: 30m, 2h, 1d",
        ganadores="Cantidad de ganadores (por defecto 1)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def create(
        self,
        interaction: discord.Interaction,
        premio: app_commands.Range[str, 1, 200],
        duracion: str,
        ganadores: app_commands.Range[int, 1, 20] = 1,
    ):
        seconds = parse_duration(duracion)
        if not seconds or seconds < 10 or seconds > 30 * 86400:
            return await interaction.response.send_message(
                embed=error("Duración inválida. Usá por ejemplo `30m`, `2h` o `1d` (entre 10s y 30d)."), ephemeral=True
            )
        end_time = time.time() + seconds
        embed = discord.Embed(
            title=f"🎁 {premio}",
            description=(
                f"Tocá el botón para participar.\n\n"
                f"⏰ Termina: <t:{int(end_time)}:R>\n"
                f"🏆 Ganadores: **{ganadores}**\n"
                f"👤 Organiza: {interaction.user.mention}"
            ),
            color=BRAND_COLOR,
        )
        embed.set_footer(text="Dilu's Bot")
        await interaction.response.send_message(embed=embed, view=GiveawayView())
        msg = await interaction.original_response()
        await self.bot.db.execute(
            "INSERT INTO giveaways (message_id, guild_id, channel_id, host_id, prize, winners, end_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg.id, interaction.guild_id, interaction.channel_id, interaction.user.id, premio, ganadores, end_time),
        )

    @sorteo.command(name="terminar", description="Termina un sorteo ahora mismo")
    @app_commands.describe(mensaje_id="ID del mensaje del sorteo (clic derecho > Copiar ID)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def end(self, interaction: discord.Interaction, mensaje_id: str):
        if not mensaje_id.isdigit():
            return await interaction.response.send_message(embed=error("ID inválido."), ephemeral=True)
        row = await self.bot.db.fetchone(
            "SELECT 1 FROM giveaways WHERE message_id = ? AND guild_id = ? AND ended = 0",
            (int(mensaje_id), interaction.guild_id),
        )
        if not row:
            return await interaction.response.send_message(embed=error("No encontré un sorteo activo con ese ID."), ephemeral=True)
        await interaction.response.send_message(embed=ok("Finalizando el sorteo..."), ephemeral=True)
        await self.finish(int(mensaje_id))


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
