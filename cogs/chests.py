import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from utils import chest_config as cc
from utils.chest_render import build_reel, render_open_gif, render_result_png
from utils.chests import ChestError, ChestService
from utils.embeds import error, make_embed, ok

log = logging.getLogger("dilus-bot.chests")

COIN = "🪙"
REEL_WAIT = 3.6          # segundos que se ve la ruleta antes de mostrar el resultado
WIN_INDEX = 31           # posición del premio real dentro de la ruleta
RARITY_CHOICES = [app_commands.Choice(name=f"{cc.RARITY_EMOJI[r]} {cc.RARITY_NAME[r]}", value=r) for r in cc.RARITIES]


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def rarity_label(r: str) -> str:
    return f"{cc.RARITY_EMOJI[r]} {cc.RARITY_NAME[r]}"


# ----------------------------------------------------------------------
# Botones
# ----------------------------------------------------------------------
class OwnedView(discord.ui.View):
    """Vista que solo puede usar quien ejecutó el comando."""

    def __init__(self, cog: "Chests", owner_id: int, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.cog, self.owner_id = cog, owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(embed=error("Estos botones son de otra persona. Usá `/cofre info` para ver los tuyos."), ephemeral=True)
            return False
        return True

    def button(self, label: str, callback, *, emoji: str | None = None, style=discord.ButtonStyle.secondary, disabled: bool = False):
        b = discord.ui.Button(label=label, emoji=emoji, style=style, disabled=disabled)
        b.callback = callback
        self.add_item(b)
        return b


class ChestActions(OwnedView):
    """Botones comunes: abrir el diario, abrir un comprado, ver el inventario."""

    def __init__(self, cog: "Chests", owner_id: int, *, daily: bool = False, open_rarities: list[str] | None = None, inventory: bool = True):
        super().__init__(cog, owner_id)
        if daily:
            self.button("Abrir cofre diario", self.on_daily, emoji="🎁", style=discord.ButtonStyle.success)
        for rarity in open_rarities or []:
            self.button(f"Abrir {cc.RARITY_NAME[rarity].lower()}", self._opener(rarity), emoji=cc.RARITY_EMOJI[rarity], style=discord.ButtonStyle.primary)
        if inventory:
            self.button("Inventario", self.on_inventory, emoji="🎒")

    def _opener(self, rarity: str):
        async def callback(interaction: discord.Interaction):
            await self.cog.run_open_bought(interaction, rarity)
        return callback

    async def on_daily(self, interaction: discord.Interaction):
        await self.cog.run_daily(interaction)

    async def on_inventory(self, interaction: discord.Interaction):
        embed, view = await self.cog.inventory_message(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ----------------------------------------------------------------------
# Cog
# ----------------------------------------------------------------------
class Chests(commands.Cog):
    cofre = app_commands.Group(name="cofre", description="📦 Cofres diarios y comprables (¡con animación!)", guild_only=True)
    cofreadmin = app_commands.Group(name="cofreadmin", description="🛠️ Administración de los cofres", guild_only=True,
                                    default_permissions=discord.Permissions(manage_guild=True))

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = ChestService(bot)
        self._n = 0

    def _fname(self, prefix: str, ext: str) -> str:
        self._n += 1
        return f"{prefix}_{self._n}.{ext}"

    async def _fail(self, interaction: discord.Interaction, exc: ChestError):
        """Muestra un ChestError como mensaje privado (funciona antes y después de responder)."""
        text = exc.message
        if exc.code == "cooldown" and exc.extra.get("ready_at"):
            text = f"Ya abriste tu cofre diario. Volvé <t:{int(exc.extra['ready_at'])}:R>."
        elif exc.code == "funds":
            text = f"No te alcanzan las monedas: necesitás **{fmt(exc.extra.get('needed', 0))}** {COIN} y tenés **{fmt(exc.extra.get('balance', 0))}**."
        embed = error(text)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Presentaciones (embeds)
    # ------------------------------------------------------------------
    @staticmethod
    def progression_track(streak: int, next_streak: int, available: bool) -> str:
        shown = min(next_streak, 7)
        icons, marks = [], []
        for day in range(1, 8):
            icons.append(cc.RARITY_EMOJI[cc.rarity_for_streak(day)])
            if day < shown or (day == shown and streak >= 7):
                marks.append("✅")
            elif day == shown:
                marks.append("➡️" if available else "⏳")
            else:
                marks.append("▫️")
        return " ".join(icons) + "\n" + " ".join(marks)

    async def info_embed(self, guild: discord.Guild, user: discord.abc.User):
        s = self.service
        d, inv, cfg = await s.daily_info(guild.id, user.id), await s.inventory(guild.id, user.id), await s.public_config(guild.id)
        nxt = d["next_rarity"]
        embed = make_embed("📦 Cofres de Dilu", color=cc.RARITY_COLOR[nxt])
        if d["available"]:
            when = f"🎁 **¡Tu cofre diario está listo!** Hoy toca: {rarity_label(nxt)}"
        else:
            when = f"⏳ Próximo cofre diario <t:{int(d['ready_at'])}:R> · Te va a tocar: {rarity_label(nxt)}"
        streak_line = f"🔥 Racha: **{d['streak']}** día(s) · Mejor: **{d['best_streak']}**"
        if d["streak_lost"]:
            streak_line += "\n💔 Perdiste la racha por no reclamar a tiempo: el próximo cofre es el primero otra vez."
        elif d["expires_at"] and d["available"]:
            streak_line += f"\n⚠️ Reclamalo antes de <t:{int(d['expires_at'])}:R> o perdés la racha."
        embed.description = f"{when}\n{streak_line}\n\n{self.progression_track(d['streak'], d['next_streak'], d['available'])}"
        embed.add_field(name="🎒 Tus cofres", value="\n".join(f"{rarity_label(r)}: **{inv[r]}**" for r in cc.RARITIES), inline=True)
        embed.add_field(name="🛒 Precios", value="\n".join(f"{rarity_label(r)}: **{fmt(cfg['rarities'][r]['price'])}** {COIN}" for r in cc.RARITIES), inline=True)
        embed.add_field(name="💡 Cómo funciona", value="El cofre diario es gratis cada 24 h y mejora con tu racha (día 7 = legendario). Los comprados no afectan la racha. "
                        "Solo dan monedas. `/cofre probabilidades` muestra todo.", inline=False)
        embed.set_footer(text="Dilu's Bot • Cofres")
        return embed, d, inv

    async def inventory_message(self, gid: int, uid: int):
        inv, cfg = await self.service.inventory(gid, uid), await self.service.public_config(gid)
        lines = [f"{rarity_label(r)}: **{inv[r]}**  ·  se compra a {fmt(cfg['rarities'][r]['price'])} {COIN}" for r in cc.RARITIES]
        embed = make_embed("🎒 Tu inventario de cofres", "\n".join(lines) + ("\n\nTocá un botón para abrir uno." if any(inv.values()) else "\n\nNo tenés cofres comprados. Usá `/cofre comprar`."))
        owned = [r for r in cc.RARITIES if inv[r] > 0]
        return embed, ChestActions(self, uid, open_rarities=owned, inventory=False)

    def result_embed(self, result: dict, filename: str) -> discord.Embed:
        rarity = result["rarity"]
        embed = make_embed(f"{cc.RARITY_EMOJI[rarity]} Cofre {cc.RARITY_NAME[rarity].lower()} abierto", color=cc.RARITY_COLOR[rarity])
        embed.description = f"## +{fmt(result['reward'])} {COIN}\nTramo: **{result['segment_name']}**"
        if result["source"] == "daily":
            d = result["daily"]
            embed.add_field(name="🔥 Racha", value=f"**{result['streak']}** día(s)")
            embed.add_field(name="⏭️ Próximo cofre", value=f"<t:{int(d['ready_at'])}:R>\n{rarity_label(d['next_rarity'])}")
        else:
            embed.add_field(name="🎒 Te quedan", value=f"**{result['inventory'][rarity]}** de este tipo")
        embed.add_field(name="💰 Saldo", value=f"**{fmt(result['balance'])}** {COIN}")
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text="Dilu's Bot • Cofres" + (" • Abierto desde el panel o el comando" if result["repeat"] else ""))
        return embed

    # ------------------------------------------------------------------
    # Apertura: el premio YA está sorteado y acreditado cuando se llama a esto. La animación solo lo muestra.
    # ------------------------------------------------------------------
    async def present(self, interaction: discord.Interaction, result: dict):
        rarity, uid = result["rarity"], interaction.user.id
        scale = (await self.service.settings(interaction.guild_id))["scale"]
        remaining = result["inventory"][rarity] if result["source"] == "bought" else 0
        view = ChestActions(self, uid, open_rarities=[rarity] if remaining > 0 else [])
        message = None
        try:                                                    # 1) animación de la ruleta
            items = build_reel(rarity, scale, result["reward"], result["segment"], random.Random(), win_index=WIN_INDEX)
            gif = await asyncio.to_thread(render_open_gif, rarity, items, WIN_INDEX)
            name = self._fname("cofre_ruleta", "gif")
            opening = make_embed(f"{cc.RARITY_EMOJI[rarity]} Abriendo cofre {cc.RARITY_NAME[rarity].lower()}…", "¡Que salga algo bueno! 🤞", color=cc.RARITY_COLOR[rarity])
            opening.set_image(url=f"attachment://{name}")
            message = await interaction.followup.send(embed=opening, file=discord.File(gif, filename=name), wait=True)
            await asyncio.sleep(REEL_WAIT)
        except Exception:
            log.exception("No pude animar la apertura; se muestra el resultado igual (las monedas ya estaban acreditadas).")
        # 2) resultado
        sub = f"Racha: {result['streak']} día(s) · Cofre diario" if result["source"] == "daily" else "Cofre comprado"
        png = await asyncio.to_thread(render_result_png, rarity, result["reward"], result["segment"], "", sub)
        fname = self._fname("cofre_resultado", "png")
        embed = self.result_embed(result, fname)
        try:
            if message is not None:
                await message.edit(embed=embed, attachments=[discord.File(png, filename=fname)], view=view)
            else:
                await interaction.followup.send(embed=embed, file=discord.File(png, filename=fname), view=view)
        except discord.HTTPException:
            log.warning("No pude mostrar el resultado del cofre (¿borraron el mensaje?).")

    async def run_daily(self, interaction: discord.Interaction):
        try:
            result = await self.service.claim_daily(interaction.guild_id, interaction.user.id, str(interaction.id))
        except ChestError as exc:
            return await self._fail(interaction, exc)
        if not interaction.response.is_done():
            await interaction.response.defer()
        await self.present(interaction, result)

    async def run_open_bought(self, interaction: discord.Interaction, rarity: str):
        try:
            result = await self.service.open_bought(interaction.guild_id, interaction.user.id, rarity, str(interaction.id))
        except ChestError as exc:
            return await self._fail(interaction, exc)
        if not interaction.response.is_done():
            await interaction.response.defer()
        await self.present(interaction, result)

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------
    @cofre.command(name="info", description="Tu racha, tu próximo cofre gratis, tus cofres y los precios")
    async def info(self, interaction: discord.Interaction):
        embed, d, inv = await self.info_embed(interaction.guild, interaction.user)
        view = ChestActions(self, interaction.user.id, daily=d["available"], open_rarities=[r for r in cc.RARITIES if inv[r] > 0][:3])
        await interaction.response.send_message(embed=embed, view=view)

    @cofre.command(name="abrir", description="Reclamá y abrí tu cofre diario gratis")
    async def abrir(self, interaction: discord.Interaction):
        await self.run_daily(interaction)

    @cofre.command(name="inventario", description="Mirá los cofres que compraste y todavía no abriste")
    async def inventario(self, interaction: discord.Interaction):
        embed, view = await self.inventory_message(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @cofre.command(name="comprar", description="Comprá cofres con tus monedas (se guardan en tu inventario)")
    @app_commands.describe(rareza="Qué tipo de cofre querés", cantidad="Cuántos (de 1 a 10)")
    @app_commands.choices(rareza=RARITY_CHOICES)
    async def comprar(self, interaction: discord.Interaction, rareza: app_commands.Choice[str], cantidad: app_commands.Range[int, 1, cc.MAX_BUY_QTY] = 1):
        try:
            r = await self.service.buy(interaction.guild_id, interaction.user.id, rareza.value, cantidad, str(interaction.id))
        except ChestError as exc:
            return await self._fail(interaction, exc)
        rar = r["rarity"]
        embed = ok(f"Compraste **{r['qty']}** × {rarity_label(rar)} por **{fmt(r['total'])}** {COIN}.\n"
                   f"Ahora tenés **{r['inventory'][rar]}** y te quedan **{fmt(r['balance'])}** {COIN}.")
        view = ChestActions(self, interaction.user.id, open_rarities=[rar])
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @cofre.command(name="abrir_comprado", description="Abrí uno de los cofres que compraste")
    @app_commands.describe(rareza="Qué tipo de cofre querés abrir")
    @app_commands.choices(rareza=RARITY_CHOICES)
    async def abrir_comprado(self, interaction: discord.Interaction, rareza: app_commands.Choice[str]):
        await self.run_open_bought(interaction, rareza.value)

    @cofre.command(name="ranking", description="Las mejores rachas de cofres del servidor")
    async def ranking(self, interaction: discord.Interaction):
        rows = await self.service.ranking(interaction.guild_id, 10)
        if not rows:
            return await interaction.response.send_message(embed=error("Todavía nadie abrió un cofre diario."), ephemeral=True)
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, r in enumerate(rows):
            member = interaction.guild.get_member(r["user_id"])
            name = member.display_name if member else f"<@{r['user_id']}>"
            lines.append(f"{medals[i] if i < 3 else f'**{i + 1}.**'} {name} · mejor racha **{r['best']}** · actual **{r['streak']}** 🔥")
        await interaction.response.send_message(embed=make_embed("🏆 Ranking de rachas de cofres", "\n".join(lines)))

    @cofre.command(name="probabilidades", description="Mirá las probabilidades y los premios de cada cofre")
    async def probabilidades(self, interaction: discord.Interaction):
        cfg = await self.service.public_config(interaction.guild_id)
        embed = make_embed("🎲 Probabilidades de los cofres", "Los cofres **solo dan monedas**. Todo se sortea en el servidor.")
        for r in cc.RARITIES:
            c = cfg["rarities"][r]
            rows = "\n".join(f"`{s['pct']:>4}%` {s['name']}: {fmt(s['lo'])}–{fmt(s['hi'])}" for s in c["segments"])
            embed.add_field(name=f"{rarity_label(r)} · {fmt(c['price'])} {COIN}", value=f"{rows}\nPromedio: **{fmt(round(c['ev']))}** {COIN} ({c['return_pct']}% del precio)", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Administración
    # ------------------------------------------------------------------
    @cofreadmin.command(name="estadisticas", description="Cofres abiertos y monedas entregadas")
    async def admin_stats(self, interaction: discord.Interaction):
        st = await self.service.admin_stats(interaction.guild_id)
        embed = make_embed("📊 Estadísticas de cofres")
        for title, key in (("Últimos 7 días", "week"), ("Desde siempre", "all")):
            a = st[key]
            embed.add_field(name=title, value=(f"Abiertos: **{fmt(a['opened'])}** ({fmt(a['daily'])} diarios · {fmt(a['bought'])} comprados)\n"
                                               f"Personas: **{a['people']}**\nMonedas entregadas: **{fmt(a['paid'])}** {COIN}\n"
                                               f"Gastado en compras: **{fmt(a['spent'])}** {COIN} ({fmt(a['bought_qty'])} cofres)\n"
                                               f"**Neto a la economía: {'+' if a['net'] >= 0 else '−'}{fmt(abs(a['net']))}** {COIN}"), inline=False)
        by = st["all"]["by_rarity"]
        embed.add_field(name="Por tipo (desde siempre)", value="\n".join(f"{rarity_label(r)}: {by[r]['daily'] + by[r]['bought']} abiertos · {fmt(by[r]['coins'])} {COIN}" for r in cc.RARITIES), inline=False)
        embed.set_footer(text=f"Escala de recompensas actual: ×{st['scale']} • «Neto» positivo = los cofres están inyectando monedas")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @cofreadmin.command(name="precio", description="Cambiá el precio de un tipo de cofre")
    @app_commands.choices(rareza=RARITY_CHOICES)
    async def admin_price(self, interaction: discord.Interaction, rareza: app_commands.Choice[str], monedas: app_commands.Range[int, 1, 1_000_000]):
        try:
            await self.service.set_price(interaction.guild_id, rareza.value, monedas)
        except ChestError as exc:
            return await self._fail(interaction, exc)
        c = (await self.service.public_config(interaction.guild_id))["rarities"][rareza.value]
        await interaction.response.send_message(embed=ok(f"El cofre {rarity_label(rareza.value)} ahora cuesta **{fmt(monedas)}** {COIN}.\n"
                                                         f"Premio promedio: {fmt(round(c['ev']))} {COIN} → devuelve el **{c['return_pct']}%** del precio."), ephemeral=True)

    @cofreadmin.command(name="escala", description="Multiplicá TODAS las recompensas de los cofres (1 = valores originales)")
    @app_commands.describe(factor="Entre 0.25 y 4. Ej: 0.5 reparte la mitad, 2 el doble")
    async def admin_scale(self, interaction: discord.Interaction, factor: app_commands.Range[float, 0.25, 4.0]):
        try:
            await self.service.set_scale(interaction.guild_id, float(factor))
        except ChestError as exc:
            return await self._fail(interaction, exc)
        cfg = await self.service.public_config(interaction.guild_id)
        lines = "\n".join(f"{rarity_label(r)}: {fmt(cfg['rarities'][r]['min'])}–{fmt(cfg['rarities'][r]['max'])} (promedio {fmt(round(cfg['rarities'][r]['ev']))})" for r in cc.RARITIES)
        await interaction.response.send_message(embed=ok(f"Escala de recompensas: **×{factor}**\n{lines}"), ephemeral=True)

    @cofreadmin.command(name="reiniciar_racha", description="Reiniciá la racha de cofres de una persona")
    @app_commands.describe(miembro="A quién", reclamar_ya="También permitirle reclamar el cofre ahora mismo")
    async def admin_reset(self, interaction: discord.Interaction, miembro: discord.Member, reclamar_ya: bool = False):
        await self.service.reset_streak(interaction.guild_id, miembro.id, reclamar_ya)
        await interaction.response.send_message(embed=ok(f"Reinicié la racha de cofres de {miembro.mention}." + (" Puede reclamar ya." if reclamar_ya else "")), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Chests(bot))
