import asyncio
import io
import logging
import random
import time

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter

from utils.embeds import BRAND_COLOR, error
from utils.fonts import fit_font, get_font

log = logging.getLogger("dilus-bot.blackjack")

# ---------- Configuración (tocá estos valores a gusto) ----------
COIN = "🪙"
MIN_BET, MAX_BET = 10, 10_000
DECKS = 6                 # cantidad de mazos en el zapato
DEALER_DELAY = 1.0        # segundos entre cada carta que saca el dealer
IDLE_TIMEOUT = 90         # segundos sin tocar nada: se planta solo
# -----------------------------------------------------------------

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RED_SUITS = {"♥", "♦"}


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ----------------------------------------------------------------------
# Lógica del juego
# ----------------------------------------------------------------------
def card_points(rank: str) -> int:
    if rank == "A":
        return 11
    if rank in ("J", "Q", "K"):
        return 10
    return int(rank)


def hand_value(cards: list[tuple[str, str]]) -> int:
    total = sum(card_points(r) for r, _ in cards)
    aces = sum(1 for r, _ in cards if r == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards: list[tuple[str, str]]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


class Game:
    def __init__(self, guild_id: int, user_id: int, bet: int):
        self.guild_id = guild_id
        self.user_id = user_id
        self.base_bet = bet
        self.bet = bet                      # sube al doblar
        self.shoe = [(r, s) for _ in range(DECKS) for s in SUITS for r in RANKS]
        random.shuffle(self.shoe)
        self.player = [self.shoe.pop(), self.shoe.pop()]
        self.dealer = [self.shoe.pop(), self.shoe.pop()]
        self.hide_hole = True
        self.doubled = False
        self.outcome: str | None = None     # None mientras se juega
        self.payout = 0
        self.note = ""


def initial_outcome(game: Game) -> str | None:
    pb, db = is_blackjack(game.player), is_blackjack(game.dealer)
    if pb and db:
        return "push"
    if pb:
        return "blackjack"
    if db:
        return "dealer_blackjack"
    return None


def final_outcome(game: Game) -> str:
    p, d = hand_value(game.player), hand_value(game.dealer)
    if p > 21:
        return "bust"
    if d > 21:
        return "dealer_bust"
    if p > d:
        return "win"
    if p < d:
        return "lose"
    return "push"


def payout_for(outcome: str, bet: int) -> int:
    """Total que se devuelve al jugador (la apuesta ya se había descontado)."""
    if outcome == "blackjack":
        return bet * 5 // 2          # paga 3 a 2
    if outcome in ("win", "dealer_bust"):
        return bet * 2
    if outcome == "push":
        return bet
    return 0


# ----------------------------------------------------------------------
# Imagen de la mesa
# ----------------------------------------------------------------------
W, H = 900, 540
CW, CH = 112, 156
MAX_STEP = 98            # separación entre cartas (se achica solo si hay muchas)
ROW_WIDTH = W - 92       # ancho disponible para una mano
GOLD = (212, 175, 55)

BANNERS = {
    "blackjack": ("★ BLACKJACK ★", (217, 160, 20)),
    "win": ("GANASTE", (34, 150, 80)),
    "dealer_bust": ("EL DEALER SE PASÓ", (34, 150, 80)),
    "lose": ("PERDISTE", (190, 45, 55)),
    "bust": ("TE PASASTE", (190, 45, 55)),
    "dealer_blackjack": ("BLACKJACK DEL DEALER", (190, 45, 55)),
    "push": ("EMPATE", (100, 110, 125)),
}


def _felt() -> Image.Image:
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    center, edge = (24, 124, 80), (8, 56, 36)
    for y in range(H):
        t = min(1.0, abs(y - H / 2) / (H / 2)) ** 1.6
        d.line([(0, y), (W, y)], fill=tuple(int(center[i] + (edge[i] - center[i]) * t) for i in range(3)))
    return img.convert("RGBA")


def _rounded_mask(w: int, h: int, radius: int) -> Image.Image:
    big = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * 4 - 1, h * 4 - 1), radius=radius * 4, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def _draw_card(img: Image.Image, x: int, y: int, card: tuple[str, str] | None):
    # sombra suave
    pad = 24
    shadow = Image.new("RGBA", (CW + pad * 2, CH + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad + 3, pad + 7, pad + CW + 3, pad + CH + 7), radius=12, fill=(0, 0, 0, 130))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)), (x - pad, y - pad))

    d = ImageDraw.Draw(img)
    if card is None:  # carta boca abajo
        tile = Image.new("RGBA", (CW, CH), (28, 52, 128, 255))
        td = ImageDraw.Draw(tile)
        for k in range(-CH, CW + CH, 14):
            td.line([(k, 0), (k + CH, CH)], fill=(52, 84, 170, 255), width=2)
            td.line([(k, CH), (k + CH, 0)], fill=(52, 84, 170, 255), width=2)
        td.rounded_rectangle((9, 9, CW - 10, CH - 10), radius=8, outline=(226, 232, 255, 255), width=3)
        img.paste(tile, (x, y), _rounded_mask(CW, CH, 12))
        d.rounded_rectangle((x, y, x + CW, y + CH), radius=12, outline=(14, 24, 70, 255), width=2)
        return

    rank, suit = card
    d.rounded_rectangle((x, y, x + CW, y + CH), radius=12, fill=(251, 251, 249, 255), outline=(172, 172, 172, 255), width=2)
    color = (196, 30, 44, 255) if suit in RED_SUITS else (24, 24, 30, 255)
    f_rank, f_small, f_big = get_font(32), get_font(26), get_font(72)
    d.text((x + 10, y + 6), rank, font=f_rank, fill=color)
    d.text((x + 11, y + 42), suit, font=f_small, fill=color)
    d.text((x + CW // 2, y + CH // 2 + 8), suit, font=f_big, fill=color, anchor="mm")
    d.text((x + CW - 10, y + CH - 8), rank, font=f_rank, fill=color, anchor="rd")


def _draw_hand(img: Image.Image, cards, x0: int, y: int, hide_second: bool = False):
    n = len(cards)
    step = MAX_STEP if n <= 1 else min(MAX_STEP, (ROW_WIDTH - CW) // (n - 1))
    for i, card in enumerate(cards):
        _draw_card(img, x0 + i * step, y, None if (hide_second and i == 1) else card)


def render_table(player, dealer, hide_hole: bool, bet: int, outcome: str | None) -> io.BytesIO:
    img = _felt()
    d = ImageDraw.Draw(img)

    # marco dorado
    d.rounded_rectangle((10, 10, W - 10, H - 10), radius=28, outline=GOLD + (255,), width=4)
    d.rounded_rectangle((20, 20, W - 20, H - 20), radius=22, outline=GOLD + (110,), width=1)

    label = get_font(24)
    dealer_total = "?" if hide_hole else str(hand_value(dealer))
    d.text((46, 34), f"DEALER  ·  {dealer_total}", font=label, fill=(244, 228, 160, 255))
    d.text((46, 306), f"TU MANO  ·  {hand_value(player)}", font=label, fill=(244, 228, 160, 255))

    _draw_hand(img, dealer, 46, 68, hide_second=hide_hole)
    _draw_hand(img, player, 46, 346)

    # ficha con la apuesta
    cx, cy, r = W - 96, 268, 44
    d = ImageDraw.Draw(img)
    d.text((cx, cy - r - 16), "APUESTA", font=get_font(16), fill=(244, 228, 160, 255), anchor="mm")
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(176, 28, 48, 255), outline=(255, 255, 255, 255), width=3)
    d.ellipse((cx - r + 9, cy - r + 9, cx + r - 9, cy + r - 9), outline=(255, 255, 255, 230), width=2)
    bet_text = fmt(bet)
    d.text((cx, cy), bet_text, font=fit_font(d, bet_text, 2 * r - 26, 24, 12), fill="white", anchor="mm")

    # cartel de resultado
    if outcome in BANNERS:
        text, color = BANNERS[outcome]
        font = fit_font(d, text, 440, 36, 20)
        tw = int(d.textlength(text, font=font))
        bx, by = 400, 268
        d.rounded_rectangle((bx - tw // 2 - 30, by - 28, bx + tw // 2 + 30, by + 28), radius=28, fill=color + (245,), outline=(255, 255, 255, 235), width=3)
        d.text((bx, by + 1), text, font=font, fill="white", anchor="mm")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf


# ----------------------------------------------------------------------
# Botones
# ----------------------------------------------------------------------
class PlayAgainView(discord.ui.View):
    def __init__(self, cog: "Blackjack", owner: discord.abc.User, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.owner = owner
        self.bet = bet
        self.message: discord.Message | None = None
        self.again.label = f"Otra mano · {fmt(bet)}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("Esta no es tu partida. Usá `/blackjack` para jugar la tuya.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Otra mano", emoji="🔁", style=discord.ButtonStyle.success)
    async def again(self, interaction: discord.Interaction, button: discord.ui.Button):
        game, err = await self.cog.deal(interaction.guild_id, self.owner, self.bet)
        if err:
            return await interaction.response.send_message(embed=error(err), ephemeral=True)
        self.stop()
        try:
            embed, file = await self.cog.build(game, self.owner)
            view = self.cog.make_view(game, self.owner, interaction.message)
            await interaction.response.edit_message(embed=embed, attachments=[file], view=view)
        except Exception:
            await self.cog.abort(game)
            raise

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class BlackjackView(discord.ui.View):
    def __init__(self, cog: "Blackjack", owner: discord.abc.User, game: Game, message: discord.Message | None = None):
        super().__init__(timeout=IDLE_TIMEOUT)
        self.cog = cog
        self.owner = owner
        self.game = game
        self.message = message
        self.lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("Esta no es tu partida. Usá `/blackjack` para jugar la tuya.", ephemeral=True)
            return False
        return True

    # ---- mostrar el estado actual ----
    async def push(self, interaction: discord.Interaction | None, view):
        embed, file = await self.cog.build(self.game, self.owner)
        kwargs = {"embed": embed, "attachments": [file], "view": view}
        if interaction is not None:
            if not interaction.response.is_done():
                await interaction.response.edit_message(**kwargs)
            else:
                await interaction.edit_original_response(**kwargs)
        elif self.message is not None:
            await self.message.edit(**kwargs)

    # ---- turno del dealer y liquidación ----
    async def finish(self, interaction: discord.Interaction | None):
        g = self.game
        g.hide_hole = False
        bust = hand_value(g.player) > 21
        try:
            await self.push(interaction, None)  # da vuelta la carta oculta, sin botones
            if not bust:
                while hand_value(g.dealer) < 17:
                    await asyncio.sleep(DEALER_DELAY)
                    g.dealer.append(g.shoe.pop())
                    await self.push(interaction, None)
        except discord.HTTPException:
            log.warning("No pude animar el turno del dealer; se resuelve igual.")
            while not bust and hand_value(g.dealer) < 17:
                g.dealer.append(g.shoe.pop())

        g.outcome = final_outcome(g)
        await self.cog.settle(g)
        self.stop()

        again = PlayAgainView(self.cog, self.owner, g.base_bet)
        again.message = interaction.message if interaction is not None else self.message
        try:
            await self.push(interaction, again)
        except discord.HTTPException:
            log.warning("No pude mostrar el resultado final de la partida.")

    # ---- botones ----
    @discord.ui.button(label="Pedir", emoji="🃏", style=discord.ButtonStyle.primary)
    async def btn_hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.lock:
            g = self.game
            if g.outcome:
                return await interaction.response.defer()
            g.player.append(g.shoe.pop())
            self.btn_double.disabled = True
            total = hand_value(g.player)
            if total >= 21:  # se pasó, o llegó a 21 y se planta solo
                await self.finish(interaction)
            else:
                await self.push(interaction, self)

    @discord.ui.button(label="Plantarse", emoji="✋", style=discord.ButtonStyle.secondary)
    async def btn_stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.lock:
            if self.game.outcome:
                return await interaction.response.defer()
            await self.finish(interaction)

    @discord.ui.button(label="Doblar", emoji="💰", style=discord.ButtonStyle.success)
    async def btn_double(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.lock:
            g = self.game
            if g.outcome or g.doubled or len(g.player) != 2:
                return await interaction.response.defer()
            if not await self.cog.eco.add(g.guild_id, g.user_id, -g.base_bet):
                return await interaction.response.send_message(
                    embed=error("No te alcanzan las monedas para doblar."), ephemeral=True
                )
            g.bet += g.base_bet
            g.doubled = True
            g.player.append(g.shoe.pop())  # recibe una sola carta y se planta
            await self.finish(interaction)

    async def on_timeout(self):
        async with self.lock:
            if self.game.outcome:
                return
            self.game.note = "⏰ Tardaste demasiado: me planté por vos."
            try:
                await self.finish(None)
            except Exception:
                log.exception("Error al cerrar una partida por tiempo")
                await self.cog.settle(self.game, force_loss=True)


# ----------------------------------------------------------------------
# Cog
# ----------------------------------------------------------------------
RESULT_TEXT = {
    "blackjack": "★ **¡BLACKJACK!** ★ Ganaste **+{net}** {coin} (paga 3 a 2)",
    "win": "¡Ganaste con {p} contra {d}! **+{net}** {coin}",
    "dealer_bust": "El dealer se pasó con {d}. ¡Ganaste! **+{net}** {coin}",
    "lose": "El dealer gana con {d} contra tus {p}. Perdiste **−{net}** {coin}",
    "bust": "Te pasaste con {p}. Perdiste **−{net}** {coin}",
    "dealer_blackjack": "El dealer tiene Blackjack. Perdiste **−{net}** {coin}",
    "push": "Empate con {p}: te devuelvo tu apuesta.",
}
RESULT_COLOR = {
    "blackjack": 0xF59E0B, "win": 0x22C55E, "dealer_bust": 0x22C55E,
    "lose": 0xEF4444, "bust": 0xEF4444, "dealer_blackjack": 0xEF4444, "push": 0x6B7280,
}


class Blackjack(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active: dict[tuple[int, int], float] = {}
        self._n = 0

    @property
    def eco(self):
        return self.bot.get_cog("Economy")

    # ---- flujo de una mano ----
    async def deal(self, guild_id: int, user: discord.abc.User, bet: int):
        """Cobra la apuesta y reparte. Devuelve (juego, None) o (None, mensaje_de_error)."""
        if self.eco is None:
            return None, "La economía no está activa, así que no se puede apostar."
        key = (guild_id, user.id)
        started = self.active.get(key)
        if started and time.time() - started < 600:
            return None, "Ya tenés una partida en juego. Terminala primero."
        if not await self.eco.add(guild_id, user.id, -bet):
            return None, "No tenés suficientes monedas para esa apuesta."

        self.active[key] = time.time()
        game = Game(guild_id, user.id, bet)
        outcome = initial_outcome(game)
        if outcome:  # Blackjack natural (propio o del dealer): se resuelve al instante
            game.hide_hole = False
            game.outcome = outcome
            await self.settle(game)
        return game, None

    async def settle(self, game: Game, force_loss: bool = False):
        game.payout = 0 if force_loss else payout_for(game.outcome or "lose", game.bet)
        if game.payout:
            await self.eco.add(game.guild_id, game.user_id, game.payout)
        self.active.pop((game.guild_id, game.user_id), None)

    async def abort(self, game: Game):
        """Si no se pudo mostrar la mesa, se devuelve la apuesta."""
        if game.outcome is None:
            await self.eco.add(game.guild_id, game.user_id, game.bet)
            self.active.pop((game.guild_id, game.user_id), None)

    def make_view(self, game: Game, user: discord.abc.User, message=None):
        if game.outcome:
            view = PlayAgainView(self, user, game.base_bet)
            view.message = message
            return view
        return BlackjackView(self, user, game, message)

    async def build(self, game: Game, user: discord.abc.User):
        buf = await asyncio.to_thread(render_table, game.player, game.dealer, game.hide_hole, game.bet, game.outcome)
        self._n += 1
        filename = f"blackjack_{self._n}.png"
        p, d = hand_value(game.player), hand_value(game.dealer)

        if game.outcome:
            net = abs(game.payout - game.bet)
            text = RESULT_TEXT[game.outcome].format(p=p, d=d, net=fmt(net), coin=COIN)
            color = RESULT_COLOR[game.outcome]
        else:
            upcard = card_points(game.dealer[0][0])
            text = f"Tu mano vale **{p}** y el dealer muestra **{upcard}**.\nElegí qué hacer con los botones de abajo."
            color = BRAND_COLOR
        if game.note:
            text += f"\n{game.note}"

        embed = discord.Embed(title=f"🃏 Blackjack · {user.display_name}", description=text, color=color)
        embed.add_field(name="Apuesta", value=f"{fmt(game.bet)} {COIN}" + (" (doblada)" if game.doubled else ""))
        if game.outcome and self.eco:
            embed.add_field(name="Saldo", value=f"{fmt(await self.eco.balance(game.guild_id, game.user_id))} {COIN}")
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text="Dilu's Bot • Blackjack paga 3:2 • El dealer se planta en 17")
        return embed, discord.File(buf, filename=filename)

    # ---- comando ----
    @app_commands.command(name="blackjack", description="🃏 Jugá al Blackjack contra el dealer apostando monedas")
    @app_commands.describe(apuesta=f"Monedas a apostar ({MIN_BET} a {fmt(MAX_BET)})")
    @app_commands.guild_only()
    async def blackjack(self, interaction: discord.Interaction, apuesta: app_commands.Range[int, MIN_BET, MAX_BET]):
        game, err = await self.deal(interaction.guild_id, interaction.user, apuesta)
        if err:
            return await interaction.response.send_message(embed=error(err), ephemeral=True)

        await interaction.response.defer()
        try:
            embed, file = await self.build(game, interaction.user)
            view = self.make_view(game, interaction.user)
            msg = await interaction.followup.send(embed=embed, file=file, view=view, wait=True)
        except Exception:
            await self.abort(game)
            raise
        view.message = msg


async def setup(bot: commands.Bot):
    await bot.add_cog(Blackjack(bot))
