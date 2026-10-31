import asyncio
import io
import logging
import time
from collections import deque

import discord
from discord import app_commands
from discord.ext import commands

from utils import roulette as rl
from utils.embeds import error, ok

log = logging.getLogger("dilus-bot.roulette")

# ---------- Configuración (tocá estos valores a gusto) ----------
COIN = "🪙"
MIN_BET, MAX_BET = 10, 10_000   # por cada apuesta
MAX_BETS_PER_PLAYER = 8         # apuestas distintas que puede tener una persona por ronda
BET_TIME = 45                   # segundos que la mesa queda abierta (se puede cambiar en /ruleta)
SPIN_WAIT = 6.5                 # segundos que dura la animación antes de mostrar el resultado
GOLD = 0xD4AF37
# -----------------------------------------------------------------


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def parse_amount(text: str) -> int | None:
    """Acepta 500, 1.000, 1,000 y 1k / 2.5k."""
    s = text.strip().lower().replace(" ", "")
    try:
        if s.endswith("k"):
            return int(round(float(s[:-1].replace(",", ".")) * 1000))
        return int(s.replace(".", "").replace(",", ""))
    except ValueError:
        return None


# ----------------------------------------------------------------------
# Mesa
# ----------------------------------------------------------------------
class Table:
    """Una mesa de ruleta abierta en un canal."""

    def __init__(self, guild_id: int, channel_id: int, host: discord.abc.User, bet_time: int):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.host_id = host.id
        self.host_name = host.display_name
        self.end_time = time.time() + bet_time + 2     # +2 s por lo que tarda en aparecer la mesa
        self.phase = "betting"                         # betting -> spinning -> done
        self.bets: dict[int, dict[str, int]] = {}      # persona -> {apuesta: monedas}
        self.message: discord.Message | None = None
        self.view: discord.ui.View | None = None
        self.task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.spin_event = asyncio.Event()
        self.settled = False
        self.dirty = False
        self.refresh_task: asyncio.Task | None = None

    def chips(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for bets in self.bets.values():
            for key, amount in bets.items():
                out[key] = out.get(key, 0) + amount
        return out

    def pot(self) -> int:
        return sum(sum(b.values()) for b in self.bets.values())


# ----------------------------------------------------------------------
# Ventanas y botones
# ----------------------------------------------------------------------
class BetModal(discord.ui.Modal):
    def __init__(self, cog: "Roulette", table: Table, key: str):
        straight = key == "straight"
        title = "Apostar a un número" if straight else f"Apostar · {rl.bet_info(key).label}"
        super().__init__(title=title[:45])
        self.cog, self.table, self.key = cog, table, key
        self.number: discord.ui.TextInput | None = None
        if straight:
            self.number = discord.ui.TextInput(label="Número (del 0 al 36)", placeholder="Ej: 17", min_length=1, max_length=2)
            self.add_item(self.number)
        self.amount = discord.ui.TextInput(
            label=f"Monedas a apostar ({MIN_BET}-{fmt(MAX_BET)})", placeholder="Ej: 500  (también vale 1k)", min_length=1, max_length=9
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key
        if self.number is not None:
            try:
                n = int(self.number.value.strip())
            except ValueError:
                n = -1
            if not 0 <= n <= 36:
                return await interaction.response.send_message(embed=error("El número tiene que ser del 0 al 36."), ephemeral=True)
            key = f"n{n}"

        amount = parse_amount(self.amount.value)
        if amount is None:
            return await interaction.response.send_message(
                embed=error("No entendí el monto. Escribí solo números, por ejemplo `500` o `1k`."), ephemeral=True
            )
        if not MIN_BET <= amount <= MAX_BET:
            return await interaction.response.send_message(
                embed=error(f"Cada apuesta tiene que estar entre **{MIN_BET}** y **{fmt(MAX_BET)}** {COIN}."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        err = await self.cog.place_bet(self.table, interaction.user, key, amount)
        if err:
            return await interaction.followup.send(embed=error(err), ephemeral=True)

        info = rl.bet_info(key)
        mine = self.table.bets[interaction.user.id]
        total_here = mine[key]
        saldo = await self.cog.eco.balance(self.table.guild_id, interaction.user.id)
        extra = f" (ahora tenés **{fmt(total_here)}** en esa apuesta)" if total_here > amount else ""
        text = (
            f"Apostaste **{fmt(amount)}** {COIN} a {info.emoji} **{info.label}**{extra}\n"
            f"Si sale, cobrás **{fmt(total_here * info.mult)}** {COIN} (ganás **+{fmt(total_here * info.ratio)}**) · "
            f"Chances: **{rl.pct(info.count)}**\n"
            f"Total en la mesa: **{fmt(sum(mine.values()))}** {COIN} · Te quedan **{fmt(saldo)}** {COIN}"
        )
        await interaction.followup.send(embed=ok(text), ephemeral=True)


def _select_options() -> list[discord.SelectOption]:
    options = []
    for b in [*rl.BET_TYPES.values(), rl.STRAIGHT]:
        desc = f"Paga {b.ratio}:1 · {rl.pct(b.count)} · {b.hint}"
        options.append(discord.SelectOption(label=b.label, value=b.key, description=desc[:100], emoji=b.emoji))
    return options


class RouletteView(discord.ui.View):
    """Botones de la mesa mientras se apuesta. Los puede usar cualquiera del chat."""

    def __init__(self, cog: "Roulette", table: Table):
        super().__init__(timeout=None)
        self.cog = cog
        self.table = table

    async def _closed(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=error("La mesa ya cerró. ¡Esperá la próxima ronda!"), ephemeral=True)

    async def ask_amount(self, interaction: discord.Interaction, key: str, reset_menu: bool = False):
        if self.table.phase != "betting":
            return await self._closed(interaction)
        if reset_menu:
            self.cog.request_refresh(self.table)   # al editar el panel el menú vuelve a quedar sin elegir
        await interaction.response.send_modal(BetModal(self.cog, self.table, key))

    # ---- fila 0: menú con todas las apuestas ----
    @discord.ui.select(placeholder="🎯 Elegí qué apostar (mirá los pagos y chances)…", options=_select_options(), row=0)
    async def pick(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.ask_amount(interaction, select.values[0], reset_menu=True)

    # ---- fila 1: apuestas rápidas ----
    @discord.ui.button(label="Rojo", emoji="🔴", style=discord.ButtonStyle.danger, row=1)
    async def b_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_amount(interaction, "red")

    @discord.ui.button(label="Negro", emoji="⚫", style=discord.ButtonStyle.secondary, row=1)
    async def b_black(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_amount(interaction, "black")

    @discord.ui.button(label="Par", style=discord.ButtonStyle.secondary, row=1)
    async def b_even(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_amount(interaction, "even")

    @discord.ui.button(label="Impar", style=discord.ButtonStyle.secondary, row=1)
    async def b_odd(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_amount(interaction, "odd")

    @discord.ui.button(label="Número", emoji="🎯", style=discord.ButtonStyle.success, row=1)
    async def b_straight(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_amount(interaction, "straight")

    # ---- fila 2: herramientas ----
    @discord.ui.button(label="Repetir", emoji="🔁", style=discord.ButtonStyle.secondary, row=2)
    async def b_repeat(self, interaction: discord.Interaction, button: discord.ui.Button):
        t = self.table
        if t.phase != "betting":
            return await self._closed(interaction)
        last = self.cog.last_bets.get((t.channel_id, interaction.user.id))
        if not last:
            return await interaction.response.send_message(
                embed=error("No tenés apuestas de la ronda anterior en este canal."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        placed, total, problem = 0, 0, None
        for key, amount in last.items():
            problem = await self.cog.place_bet(t, interaction.user, key, amount)
            if problem:
                break
            placed += 1
            total += amount
        if not placed:
            return await interaction.followup.send(embed=error(problem), ephemeral=True)
        text = f"Repetí **{placed}** apuesta(s) de la ronda pasada por **{fmt(total)}** {COIN}."
        if problem:
            text += f"\n⚠️ El resto no entró: {problem}"
        await interaction.followup.send(embed=ok(text), ephemeral=True)

    @discord.ui.button(label="Mis apuestas", emoji="📋", style=discord.ButtonStyle.secondary, row=2)
    async def b_mine(self, interaction: discord.Interaction, button: discord.ui.Button):
        mine = self.table.bets.get(interaction.user.id)
        if not mine:
            return await interaction.response.send_message(
                embed=error("Todavía no apostaste nada en esta ronda."), ephemeral=True
            )
        lines = []
        for key, amount in mine.items():
            info = rl.bet_info(key)
            lines.append(f"{info.emoji} **{info.label}** · {fmt(amount)} {COIN} → si sale cobrás **{fmt(amount * info.mult)}**")
        embed = discord.Embed(title="📋 Tus apuestas", description="\n".join(lines), color=GOLD)
        embed.set_footer(text=f"Total apostado: {fmt(sum(mine.values()))} • Dilu's Bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Quitar", emoji="🗑️", style=discord.ButtonStyle.secondary, row=2)
    async def b_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        refunded = await self.cog.clear_bets(self.table, interaction.user)
        if refunded is None:
            return await self._closed(interaction)
        if refunded == 0:
            return await interaction.response.send_message(embed=error("No tenés apuestas para quitar."), ephemeral=True)
        await interaction.response.send_message(
            embed=ok(f"Quité tus apuestas y te devolví **{fmt(refunded)}** {COIN}."), ephemeral=True
        )

    @discord.ui.button(label="Ayuda", emoji="❓", style=discord.ButtonStyle.secondary, row=2)
    async def b_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=self.cog.how_to_embed(), ephemeral=True)

    @discord.ui.button(label="Girar ya", emoji="🎡", style=discord.ButtonStyle.primary, row=2)
    async def b_spin(self, interaction: discord.Interaction, button: discord.ui.Button):
        t = self.table
        if t.phase != "betting":
            return await self._closed(interaction)
        is_host = interaction.user.id == t.host_id
        if not is_host and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                embed=error(f"Solo quien abrió la mesa (o un admin) puede girar antes. Se cierra sola <t:{int(t.end_time)}:R>."),
                ephemeral=True,
            )
        if not t.bets:
            return await interaction.response.send_message(embed=error("Todavía no apostó nadie."), ephemeral=True)
        t.spin_event.set()
        await interaction.response.defer()


class RoundOverView(discord.ui.View):
    """Botón que aparece después del resultado."""

    def __init__(self, cog: "Roulette"):
        super().__init__(timeout=120)
        self.cog = cog
        self.message: discord.Message | None = None

    @discord.ui.button(label="Nueva ronda", emoji="🎡", style=discord.ButtonStyle.success)
    async def again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel_id in self.cog.tables:
            return await interaction.response.send_message(embed=error("Ya hay una mesa abierta en este canal."), ephemeral=True)
        self.stop()
        await interaction.response.edit_message(view=None)
        await self.cog.open_table(interaction, BET_TIME)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


# ----------------------------------------------------------------------
# Cog
# ----------------------------------------------------------------------
class Roulette(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tables: dict[int, Table] = {}                        # canal -> mesa abierta
        self.history: dict[int, deque[int]] = {}                  # servidor -> últimos números
        self.last_bets: dict[tuple[int, int], dict[str, int]] = {}  # (canal, persona) -> apuestas de la ronda anterior
        self._n = 0

    @property
    def eco(self):
        return self.bot.get_cog("Economy")

    def _fname(self, prefix: str, ext: str) -> str:
        self._n += 1
        return f"{prefix}_{self._n}.{ext}"

    # ---- arranque / cierre ----
    async def cog_load(self):
        """Si el bot se reinició en medio de una ronda, devuelve las monedas que quedaron apostadas."""
        db = self.bot.db
        rows = await db.fetchall("SELECT guild_id, user_id, SUM(amount) AS total FROM roulette_bets GROUP BY guild_id, user_id")
        for r in rows:
            await db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", (r["guild_id"], r["user_id"]))
            await db.execute(
                "UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?",
                (r["total"], r["guild_id"], r["user_id"]),
            )
        if rows:
            await db.execute("DELETE FROM roulette_bets")
            log.info("Ruleta: devolví las apuestas pendientes de %d persona(s) tras un reinicio.", len(rows))

    async def cog_unload(self):
        for table in list(self.tables.values()):
            if table.task:
                table.task.cancel()

    # ------------------------------------------------------------------
    # Apuestas
    # ------------------------------------------------------------------
    async def place_bet(self, table: Table, user: discord.abc.User, key: str, amount: int) -> str | None:
        """Cobra y anota la apuesta. Devuelve un mensaje de error, o None si salió todo bien."""
        if self.eco is None:
            return "La economía no está activa, así que no se puede apostar."
        async with table.lock:
            if table.phase != "betting":
                return "La mesa ya cerró. ¡Esperá la próxima ronda!"
            mine = table.bets.get(user.id, {})
            if key not in mine and len(mine) >= MAX_BETS_PER_PLAYER:
                return f"Podés tener hasta **{MAX_BETS_PER_PLAYER}** apuestas distintas por ronda."
            current = mine.get(key, 0)
            if current + amount > MAX_BET:
                return f"El máximo por apuesta es **{fmt(MAX_BET)}** {COIN} (en esa ya tenés {fmt(current)})."
            if not await self.eco.add(table.guild_id, user.id, -amount):
                return "No tenés suficientes monedas."
            try:
                await self.bot.db.execute(
                    "INSERT INTO roulette_bets (message_id, guild_id, user_id, bet_key, amount) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(message_id, user_id, bet_key) DO UPDATE SET amount = excluded.amount",
                    (table.message.id, table.guild_id, user.id, key, current + amount),
                )
            except Exception:
                await self.eco.add(table.guild_id, user.id, amount)   # no se pudo anotar: se devuelve
                raise
            mine[key] = current + amount
            table.bets[user.id] = mine
        self.request_refresh(table)
        return None

    async def clear_bets(self, table: Table, user: discord.abc.User) -> int | None:
        """Devuelve las monedas de todas las apuestas de la persona. None si la mesa ya cerró."""
        async with table.lock:
            if table.phase != "betting":
                return None
            mine = table.bets.pop(user.id, None)
            if not mine:
                return 0
            total = sum(mine.values())
            await self.eco.add(table.guild_id, user.id, total)
            await self.bot.db.execute(
                "DELETE FROM roulette_bets WHERE message_id = ? AND user_id = ?", (table.message.id, user.id)
            )
        self.request_refresh(table)
        return total

    # ------------------------------------------------------------------
    # Mensajes
    # ------------------------------------------------------------------
    @staticmethod
    def players_text(table: Table) -> str:
        if not table.bets:
            return "Todavía nadie apostó. ¡Animate, la mesa está abierta! 🎲"
        ranked = sorted(table.bets.items(), key=lambda kv: -sum(kv[1].values()))
        lines = [f"<@{uid}> · **{fmt(sum(b.values()))}** {COIN}" for uid, b in ranked]
        shown = lines[:10]
        if len(lines) > 10:
            shown.append(f"…y {len(lines) - 10} más")
        return "\n".join(shown)

    def panel_embed(self, table: Table, filename: str) -> discord.Embed:
        end = int(table.end_time)
        embed = discord.Embed(
            title=f"🎡 Ruleta · mesa de {table.host_name}",
            description=(
                f"**¡Mesa abierta!** Cierra <t:{end}:R> y la bola gira sola.\n\n"
                "**Cómo apostar**\n"
                "1️⃣ Elegí qué apostar en el menú o con los botones\n"
                f"2️⃣ Escribí cuántas monedas ponés ({MIN_BET} a {fmt(MAX_BET)})\n"
                "3️⃣ Esperá el giro: si sale lo tuyo, cobrás al instante\n\n"
                "*Tus fichas aparecen en el tablero, en la zona donde apostaste. ¿Dudas? Tocá* ❓ ***Ayuda***."
            ),
            color=GOLD,
        )
        embed.add_field(name="💰 En juego", value=f"**{fmt(table.pot())}** {COIN}")
        embed.add_field(name="⏱️ Cierra", value=f"<t:{end}:R>")
        embed.add_field(name=f"👥 Jugadores ({len(table.bets)})", value=self.players_text(table), inline=False)
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text="Dilu's Bot • Ruleta europea (un solo cero) • La casa tiene 2,7% de ventaja")
        return embed

    def spin_embed(self, table: Table, filename: str) -> discord.Embed:
        embed = discord.Embed(
            title="🎡 ¡No va más!",
            description=(
                "La bola está girando… 🤞\n\n"
                f"**{len(table.bets)}** jugador(es) · **{fmt(table.pot())}** {COIN} en juego"
            ),
            color=GOLD,
        )
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text="Dilu's Bot • Ruleta europea")
        return embed

    def result_embed(self, table: Table, number: int, rows: list[tuple[int, int, int]], filename: str) -> discord.Embed:
        kind = rl.color_of(number)
        lines = []
        for uid, staked, returned in sorted(rows, key=lambda r: r[2] - r[1], reverse=True):
            net = returned - staked
            if net > 0:
                lines.append(f"🟢 <@{uid}> ganó **+{fmt(net)}** {COIN}  *(apostó {fmt(staked)}, cobró {fmt(returned)})*")
            elif net == 0 and returned:
                lines.append(f"⚪ <@{uid}> recuperó lo apostado ({fmt(staked)} {COIN})")
            elif returned:
                lines.append(f"🔴 <@{uid}> perdió **{fmt(-net)}** {COIN}  *(cobró {fmt(returned)} de {fmt(staked)})*")
            else:
                lines.append(f"🔴 <@{uid}> perdió **{fmt(staked)}** {COIN}")
        shown = lines[:15]
        if len(lines) > 15:
            shown.append(f"…y {len(lines) - 15} más")

        embed = discord.Embed(
            title=f"🎡 ¡Salió el {number}! {rl.COLOR_EMOJI[kind]}",
            description=f"**{' · '.join(rl.number_tags(number))}**\n\n" + "\n".join(shown),
            color={"red": 0xEF4444, "black": 0x4B5563, "green": 0x22C55E}[kind],
        )
        embed.add_field(name="💰 Apostado", value=f"{fmt(sum(r[1] for r in rows))} {COIN}")
        embed.add_field(name="🏆 Pagado", value=f"{fmt(sum(r[2] for r in rows))} {COIN}")
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text="Dilu's Bot • ¿Otra vuelta? Tocá «Nueva ronda»")
        return embed

    @staticmethod
    def how_to_embed() -> discord.Embed:
        embed = discord.Embed(
            title="🎡 Cómo se juega a la ruleta",
            description=(
                "La rueda tiene **37 casilleros**: del **0** al **36**. Mientras la mesa está abierta, cada persona apuesta a lo que quiera. "
                "Después la bola gira, cae en un número y las apuestas ganadoras **cobran al instante**."
            ),
            color=GOLD,
        )
        embed.add_field(
            name="🔴 Apuestas simples · pagan 1 a 1",
            value=(
                "Rojo, Negro, Par, Impar, 1-18 y 19-36.\n"
                f"Cubren 18 números: chances de **{rl.pct(18)}**.\n"
                "Ej: ponés 100 y ganás → cobrás **200** (ganancia de 100)."
            ),
            inline=False,
        )
        embed.add_field(
            name="🥇 Docenas y columnas · pagan 2 a 1",
            value=(
                "Docenas: 1-12, 13-24 y 25-36. Columnas: las tres filas del tablero (las marcadas «2:1»).\n"
                f"Cubren 12 números: chances de **{rl.pct(12)}**.\n"
                "Ej: ponés 100 y ganás → cobrás **300** (ganancia de 200)."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎯 Número pleno · paga 35 a 1",
            value=(
                f"Apostás a un solo número: chances de **{rl.pct(1)}**.\n"
                "Ej: ponés 100 al 17 y sale → cobrás **3.600** (ganancia de 3.500)."
            ),
            inline=False,
        )
        embed.add_field(
            name="🟢 ¿Y el cero?",
            value="Es verde: no cuenta como rojo, negro, par, impar, bajo ni alto. Si sale, **pierden todas las apuestas** salvo la de quien apostó al 0.",
            inline=False,
        )
        embed.add_field(
            name="🎛️ Los botones",
            value=(
                "🔁 **Repetir**: vuelve a poner tus apuestas de la ronda anterior\n"
                "📋 **Mis apuestas**: ves lo que jugaste y cuánto cobrarías\n"
                "🗑️ **Quitar**: cancelás tus apuestas y te devuelvo las monedas\n"
                "🎡 **Girar ya**: solo quien abrió la mesa (o un admin)"
            ),
            inline=False,
        )
        embed.add_field(
            name="🧠 Para tener en cuenta",
            value=(
                f"Podés combinar hasta **{MAX_BETS_PER_PLAYER}** apuestas distintas. Por el cero, la casa tiene **2,7%** de ventaja: "
                "a la larga la banca gana, así que ¡jugá por diversión!"
            ),
            inline=False,
        )
        embed.set_footer(text="Dilu's Bot • Ruleta europea")
        return embed

    # ------------------------------------------------------------------
    # Panel de apuestas (se actualiza solo, sin pasarse de revoluciones)
    # ------------------------------------------------------------------
    async def build_panel(self, table: Table):
        hist = list(self.history.get(table.guild_id, []))
        buf = await asyncio.to_thread(rl.render_board, table.chips(), hist, None, "MESA ABIERTA")
        name = self._fname("ruleta", "png")
        return self.panel_embed(table, name), discord.File(buf, filename=name)

    def request_refresh(self, table: Table):
        """Pide actualizar el panel; junta varios cambios seguidos en una sola edición."""
        table.dirty = True
        if table.refresh_task is None or table.refresh_task.done():
            table.refresh_task = asyncio.create_task(self._refresh_loop(table))

    async def _refresh_loop(self, table: Table):
        await asyncio.sleep(1.2)
        while table.dirty and table.phase == "betting":
            table.dirty = False
            try:
                embed, file = await self.build_panel(table)
                async with table.lock:
                    if table.phase != "betting":
                        return
                    await table.message.edit(embed=embed, attachments=[file], view=table.view)
            except discord.HTTPException:
                log.warning("No pude actualizar el panel de la ruleta.")
            except Exception:
                log.exception("Error actualizando el panel de la ruleta")
                return
            await asyncio.sleep(2.0)

    async def _safe_edit(self, table: Table, **kwargs) -> bool:
        try:
            await table.message.edit(**kwargs)
            return True
        except discord.HTTPException:
            log.warning("No pude editar el mensaje de la ruleta (¿lo borraron?).")
            return False

    # ------------------------------------------------------------------
    # Ciclo de una mesa
    # ------------------------------------------------------------------
    async def open_table(self, interaction: discord.Interaction, bet_time: int):
        if self.eco is None:
            return await interaction.response.send_message(
                embed=error("La economía no está activa, así que no se puede apostar."), ephemeral=True
            )
        channel_id = interaction.channel_id
        if channel_id in self.tables:
            return await interaction.response.send_message(
                embed=error("Ya hay una mesa abierta en este canal. ¡Sumate a esa!"), ephemeral=True
            )

        table = Table(interaction.guild_id, channel_id, interaction.user, bet_time)
        self.tables[channel_id] = table
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
            embed, file = await self.build_panel(table)
            table.view = RouletteView(self, table)
            table.message = await interaction.followup.send(embed=embed, file=file, view=table.view, wait=True)
        except Exception:
            self.tables.pop(channel_id, None)
            raise
        table.task = asyncio.create_task(self._run(table))

    async def _run(self, table: Table):
        try:
            try:
                await asyncio.wait_for(table.spin_event.wait(), timeout=max(0.0, table.end_time - time.time()))
            except asyncio.TimeoutError:
                pass
            await self._spin(table)
        except asyncio.CancelledError:
            await self._refund_all(table)
            raise
        except Exception:
            log.exception("Error en la ruleta del canal %s", table.channel_id)
            if table.settled:
                msg = "Los pagos ya se acreditaron, pero no pude mostrar el resultado. Mirá tu `/balance`."
            else:
                await self._refund_all(table)
                msg = "Hubo un problema con la ruleta. Te devolví todas las apuestas."
            await self._safe_edit(table, embed=error(msg), attachments=[], view=None)
        finally:
            table.phase = "done"
            self.tables.pop(table.channel_id, None)

    async def _spin(self, table: Table):
        async with table.lock:
            table.phase = "spinning"           # desde acá no entran más apuestas
        if table.view:
            table.view.stop()

        if not table.bets:
            embed = discord.Embed(title="🎡 Mesa cerrada", description="Nadie apostó, así que no hubo giro. ¡Abrí otra con `/ruleta`!", color=0x6B7280)
            await self._safe_edit(table, embed=embed, attachments=[], view=None)
            return

        number = rl.spin()

        # 1) animación de la rueda
        try:
            gif = await asyncio.to_thread(rl.render_spin_gif, number)
            if gif.getbuffer().nbytes > 7_500_000:
                raise ValueError("el GIF pesa demasiado")
            name = self._fname("ruleta_giro", "gif")
            if await self._safe_edit(table, embed=self.spin_embed(table, name), attachments=[discord.File(gif, filename=name)], view=None):
                await asyncio.sleep(SPIN_WAIT)
        except Exception:
            log.exception("No pude animar la ruleta; se resuelve igual.")

        # 2) se dibuja el resultado ANTES de pagar: si algo falla acá, se devuelven las apuestas sin tocar saldos
        hist = [*self.history.get(table.guild_id, []), number]
        board = (await asyncio.to_thread(rl.render_board, table.chips(), hist, number)).getvalue()

        # 3) pagos
        rows = await self.settle(table, number)

        # 4) resultado
        name = self._fname("ruleta_resultado", "png")
        embed = self.result_embed(table, number, rows, name)
        view = RoundOverView(self)
        if await self._safe_edit(table, embed=embed, attachments=[discord.File(io.BytesIO(board), filename=name)], view=view):
            view.message = table.message
        else:  # si borraron el mensaje, igual se avisa el resultado en el canal
            channel = self.bot.get_channel(table.channel_id)
            if channel is not None:
                try:
                    await channel.send(embed=embed, file=discord.File(io.BytesIO(board), filename=name), view=view)
                except discord.HTTPException:
                    log.warning("No pude avisar el resultado de la ruleta.")

    async def settle(self, table: Table, number: int) -> list[tuple[int, int, int]]:
        """Paga a quien ganó. Devuelve [(persona, apostado, cobrado)]."""
        rows = []
        for uid, bets in table.bets.items():
            staked = sum(bets.values())
            returned = sum(rl.payout(key, amount, number) for key, amount in bets.items())
            if returned:
                await self.eco.add(table.guild_id, uid, returned)
            rows.append((uid, staked, returned))
            self.last_bets[(table.channel_id, uid)] = dict(bets)
        table.settled = True
        await self.bot.db.execute("DELETE FROM roulette_bets WHERE message_id = ?", (table.message.id,))
        self.history.setdefault(table.guild_id, deque(maxlen=20)).append(number)
        return rows

    async def _refund_all(self, table: Table):
        """Si algo sale mal, todas las apuestas vuelven a sus dueños."""
        if table.settled or table.message is None:
            return
        table.settled = True
        for uid, bets in table.bets.items():
            try:
                await self.eco.add(table.guild_id, uid, sum(bets.values()))
            except Exception:
                log.exception("No pude devolver las monedas de %s", uid)
        try:
            await self.bot.db.execute("DELETE FROM roulette_bets WHERE message_id = ?", (table.message.id,))
        except Exception:
            log.exception("No pude limpiar las apuestas de la ruleta")

    # ------------------------------------------------------------------
    # Comando
    # ------------------------------------------------------------------
    @app_commands.command(name="ruleta", description="🎡 Abrí una mesa de ruleta: todo el chat puede apostar con sus monedas")
    @app_commands.describe(tiempo=f"Segundos que la mesa queda abierta para apostar (por defecto {BET_TIME})")
    @app_commands.guild_only()
    async def ruleta(self, interaction: discord.Interaction, tiempo: app_commands.Range[int, 20, 120] = BET_TIME):
        await self.open_table(interaction, tiempo)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roulette(bot))
