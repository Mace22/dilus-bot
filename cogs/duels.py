"""Duelos de cara o cruz entre personas del servidor.

Una persona desafía a otra con una apuesta y elige cara o cruz (la otra se queda con el lado contrario).
Si el desafiado acepta, se tira la moneda y el ganador se lleva todo el pozo (el doble de la apuesta).
Se puede crear y aceptar tanto desde Discord (/caracruz duelo + botones) como desde el panel web.

La apuesta del retador queda en custodia apenas crea el duelo; se le devuelve si el otro rechaza,
no responde a tiempo, o si el bot se reinicia con duelos abiertos.
"""
import asyncio
import io
import logging
import random
import time
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.economy import COIN, MAX_BET, MIN_BET, fmt
from utils import coin_anim
from utils.embeds import error, make_embed

log = logging.getLogger("dilus-bot.duels")

DUEL_TTL = 120          # segundos que el desafío espera una respuesta
MAX_OPEN = 3            # desafíos abiertos a la vez por persona
GOLD, GREEN, RED, GREY = 0xD4AF37, 0x22C55E, 0xEF4444, 0x6B7280
OTHER = {"cara": "cruz", "cruz": "cara"}


class DuelError(Exception):
    """Error con mensaje listo para mostrar (status = código HTTP equivalente para el panel)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class DuelView(discord.ui.View):
    def __init__(self, cog: "Duels", duel_id: int, challenger_id: int, opponent_id: int):
        super().__init__(timeout=DUEL_TTL + 60)
        self.cog, self.duel_id, self.challenger_id, self.opponent_id = cog, duel_id, challenger_id, opponent_id

    async def _run(self, interaction: discord.Interaction, fn, who: int, denied: str):
        if interaction.user.id != who:
            return await interaction.response.send_message(embed=error(denied), ephemeral=True)
        await interaction.response.defer()
        try:
            await fn(self.duel_id, interaction.user.id)
        except DuelError as e:
            await interaction.followup.send(embed=error(e.message), ephemeral=True)

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._run(interaction, self.cog.accept, self.opponent_id, "Este desafío no es para vos.")

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger, emoji="✖️")
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._run(interaction, self.cog.decline, self.opponent_id, "Este desafío no es para vos.")

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._run(interaction, self.cog.cancel, self.challenger_id, "Solo quien creó el desafío puede cancelarlo.")


class Duels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.msgs: dict[int, discord.Message] = {}      # mensaje de Discord de cada duelo abierto
        self._tasks: set[asyncio.Task] = set()          # animaciones en curso
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    @property
    def db(self):
        return self.bot.db

    @property
    def eco(self):
        eco = self.bot.get_cog("Economy")
        if eco is None:
            raise DuelError("La economía del bot no está activa.", 503)
        return eco

    async def cog_load(self):
        await self._recover()
        self.sweeper.start()

    async def cog_unload(self):
        self.sweeper.cancel()
        for t in list(self._tasks):
            t.cancel()

    # ------------------------------------------------------------------
    # Reinicios y vencimientos
    # ------------------------------------------------------------------
    async def _refund_raw(self, gid: int, uid: int, amount: int):
        await self.db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", (gid, uid))
        await self.db.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (amount, gid, uid))

    async def _recover(self):
        """Si el bot se reinició con duelos abiertos, devuelve las apuestas."""
        rows = await self.db.fetchall("SELECT * FROM coin_duels WHERE status IN ('pending', 'resolving')")
        for r in rows:
            await self._refund_raw(r["guild_id"], r["challenger_id"], r["bet"])
            if r["opp_paid"]:
                await self._refund_raw(r["guild_id"], r["opponent_id"], r["bet"])
            await self.db.execute("UPDATE coin_duels SET status = 'expired', resolved = ? WHERE id = ?", (time.time(), r["id"]))
        if rows:
            log.info("Duelos: devolví las apuestas de %d duelo(s) que quedaron abiertos.", len(rows))

    @tasks.loop(seconds=10)
    async def sweeper(self):
        await self.sweep_once()

    async def sweep_once(self):
        now = time.time()
        for r in await self.db.fetchall("SELECT id FROM coin_duels WHERE status = 'pending' AND expires < ?", (now,)):
            try:
                await self._close(r["id"], None, "expired")
            except Exception:
                log.exception("No pude vencer el duelo %s", r["id"])
        await self.db.execute("DELETE FROM coin_duels WHERE status NOT IN ('pending', 'resolving') AND resolved < ?", (now - 7 * 86400,))

    @sweeper.before_loop
    async def _before_sweeper(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Presentación
    # ------------------------------------------------------------------
    @staticmethod
    def pending_embed(r) -> discord.Embed:
        embed = make_embed(
            "🪙 Duelo de cara o cruz",
            f"**{r['challenger_name']}** desafía a **{r['opponent_name']}** por **{fmt(r['bet'])}** {COIN}\n\n"
            f"🔸 {r['challenger_name']} eligió **{r['side']}**\n"
            f"🔹 {r['opponent_name']} se queda con **{OTHER[r['side']]}**\n\n"
            f"El ganador se lleva **{fmt(r['bet'] * 2)}** {COIN}.\nVence <t:{int(r['expires'])}:R>",
            color=GOLD,
        )
        return embed

    @staticmethod
    def final_embed(r) -> discord.Embed:
        st = r["status"]
        if st == "done":
            winner = r["challenger_name"] if r["winner_id"] == r["challenger_id"] else r["opponent_name"]
            loser = r["opponent_name"] if winner == r["challenger_name"] else r["challenger_name"]
            return make_embed(
                f"🪙 Salió {r['result'].upper()}",
                f"🏆 **{winner}** le ganó a **{loser}** y se lleva **{fmt(r['bet'] * 2)}** {COIN}\n"
                f"*({r['challenger_name']} había elegido {r['side']})*",
                color=GREEN,
            )
        text = {
            "declined": f"**{r['opponent_name']}** rechazó el duelo. Se devolvió la apuesta.",
            "cancelled": f"**{r['challenger_name']}** canceló el duelo. Se devolvió la apuesta.",
            "expired": f"**{r['opponent_name']}** no respondió a tiempo. Se devolvió la apuesta.",
        }[st]
        return make_embed("🪙 Duelo cerrado", text, color=GREY)

    async def _update_message(self, row):
        msg = self.msgs.pop(row["id"], None)
        if msg is None:
            return
        if row["status"] == "done":              # la moneda se tira con animación (sin frenar a quien aceptó)
            task = asyncio.create_task(self._animate(msg, row))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return
        try:
            await msg.edit(content=None, embed=self.final_embed(row), view=None)
        except discord.HTTPException:
            pass

    async def _animate(self, msg: discord.Message, row):
        """1) la moneda girando en el aire (GIF)  2) el resultado con la moneda quieta del lado que salió."""
        try:
            gif, png = await asyncio.to_thread(coin_anim.render, row["result"])
            air = make_embed(
                "🪙 ¡La moneda está en el aire!",
                f"🔸 **{row['challenger_name']}** → **{row['side']}**\n🔹 **{row['opponent_name']}** → **{OTHER[row['side']]}**\n\n"
                f"Pozo: **{fmt(row['bet'] * 2)}** {COIN}",
                color=GOLD,
            )
            air.set_image(url="attachment://moneda.gif")
            await msg.edit(content=None, embed=air, attachments=[discord.File(io.BytesIO(gif), "moneda.gif")], view=None)
            await asyncio.sleep(3.4)
            final = self.final_embed(row)
            final.set_image(url="attachment://moneda.png")
            await msg.edit(embed=final, attachments=[discord.File(io.BytesIO(png), "moneda.png")], view=None)
        except Exception:
            log.exception("No pude animar el duelo %s", row["id"])
            try:
                await msg.edit(content=None, embed=self.final_embed(row), attachments=[], view=None)
            except discord.HTTPException:
                pass

    async def announce(self, row, *, channel: discord.abc.Messageable | None = None, opponent: discord.abc.User | None = None) -> bool:
        """Publica el desafío con botones en un canal, o por mensaje privado al desafiado (si se creó desde el panel)."""
        view = DuelView(self, row["id"], row["challenger_id"], row["opponent_id"])
        try:
            if channel is not None:
                msg = await channel.send(
                    content=f"<@{row['opponent_id']}>", embed=self.pending_embed(row), view=view,
                    allowed_mentions=discord.AllowedMentions(users=[discord.Object(row["opponent_id"])]),
                )
            else:
                msg = await opponent.send(
                    content=f"🪙 **{row['challenger_name']}** te desafió a cara o cruz desde el panel web.",
                    embed=self.pending_embed(row), view=view,
                )
        except discord.HTTPException:
            return False
        self.msgs[row["id"]] = msg
        return True

    # ------------------------------------------------------------------
    # Lógica (la usan los botones, el comando y el panel web)
    # ------------------------------------------------------------------
    async def create(self, guild: discord.Guild, challenger, opponent, bet, side, *, source: str):
        if not isinstance(bet, int) or isinstance(bet, bool) or not MIN_BET <= bet <= MAX_BET:
            raise DuelError(f"La apuesta mínima es {MIN_BET} monedas.")
        if side not in OTHER:
            raise DuelError("Elegí cara o cruz.")
        if opponent.bot or opponent.id == challenger.id:
            raise DuelError("Elegí a otra persona (no bots ni vos mismo).")
        open_n = await self.db.fetchone(
            "SELECT COUNT(*) AS c FROM coin_duels WHERE guild_id = ? AND challenger_id = ? AND status = 'pending'", (guild.id, challenger.id)
        )
        if open_n["c"] >= MAX_OPEN:
            raise DuelError(f"Ya tenés {MAX_OPEN} desafíos abiertos. Esperá a que respondan o cancelá alguno.", 409)
        if not await self.eco.add(guild.id, challenger.id, -bet):
            raise DuelError("No tenés suficientes monedas para esa apuesta.", 402)
        now = time.time()
        cur = await self.db.execute(
            "INSERT INTO coin_duels (guild_id, challenger_id, challenger_name, opponent_id, opponent_name, bet, side, source, created, expires) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (guild.id, challenger.id, challenger.display_name, opponent.id, opponent.display_name, bet, side, source, now, now + DUEL_TTL),
        )
        return await self.db.fetchone("SELECT * FROM coin_duels WHERE id = ?", (cur.lastrowid,))

    async def _get(self, duel_id):
        row = await self.db.fetchone("SELECT * FROM coin_duels WHERE id = ?", (duel_id,)) if isinstance(duel_id, int) else None
        if row is None:
            raise DuelError("Ese duelo no existe.", 404)
        return row

    async def _close(self, duel_id: int, by: int | None, status: str):
        """Cierra un duelo pendiente (rechazado / cancelado / vencido) y devuelve la apuesta al retador."""
        async with self._locks[duel_id]:
            cur = await self.db.execute(
                "UPDATE coin_duels SET status = ?, resolved = ? WHERE id = ? AND status = 'pending'", (status, time.time(), duel_id)
            )
            if cur.rowcount == 0:
                return None
            row = await self.db.fetchone("SELECT * FROM coin_duels WHERE id = ?", (duel_id,))
            await self._refund_raw(row["guild_id"], row["challenger_id"], row["bet"])
        await self._update_message(row)
        return row

    async def decline(self, duel_id: int, user_id: int):
        row = await self._get(duel_id)
        if row["opponent_id"] != user_id:
            raise DuelError("Este desafío no es para vos.", 403)
        if not await self._close(duel_id, user_id, "declined"):
            raise DuelError("Ese desafío ya no está abierto.", 409)

    async def cancel(self, duel_id: int, user_id: int):
        row = await self._get(duel_id)
        if row["challenger_id"] != user_id:
            raise DuelError("Solo quien creó el desafío puede cancelarlo.", 403)
        if not await self._close(duel_id, user_id, "cancelled"):
            raise DuelError("Ese desafío ya no está abierto.", 409)

    async def accept(self, duel_id: int, user_id: int):
        row = await self._get(duel_id)
        if row["opponent_id"] != user_id:
            raise DuelError("Este desafío no es para vos.", 403)
        async with self._locks[duel_id]:
            if time.time() > row["expires"]:
                raise DuelError("Ese desafío ya venció.", 409)
            claimed = await self.db.execute("UPDATE coin_duels SET status = 'resolving' WHERE id = ? AND status = 'pending'", (duel_id,))
            if claimed.rowcount == 0:
                raise DuelError("Ese desafío ya no está abierto.", 409)
            gid, bet = row["guild_id"], row["bet"]
            if not await self.eco.add(gid, user_id, -bet):
                await self.db.execute("UPDATE coin_duels SET status = 'pending' WHERE id = ?", (duel_id,))
                raise DuelError("No tenés suficientes monedas para aceptar.", 402)
            await self.db.execute("UPDATE coin_duels SET opp_paid = 1 WHERE id = ?", (duel_id,))

            result = random.SystemRandom().choice(["cara", "cruz"])
            winner = row["challenger_id"] if result == row["side"] else row["opponent_id"]
            loser = row["opponent_id"] if winner == row["challenger_id"] else row["challenger_id"]
            await self._refund_raw(gid, winner, bet * 2)
            await self.db.execute(
                "UPDATE coin_duels SET status = 'done', result = ?, winner_id = ?, resolved = ? WHERE id = ?", (result, winner, time.time(), duel_id)
            )
            await self._record(gid, winner, bet, bet * 2, result)
            await self._record(gid, loser, bet, 0, result)
            row = await self.db.fetchone("SELECT * FROM coin_duels WHERE id = ?", (duel_id,))
        await self._update_message(row)
        return row

    async def _record(self, gid: int, uid: int, wagered: int, returned: int, detail: str):
        """Suma el duelo a las estadísticas y al historial del casino (se ve en el panel)."""
        await self.db.execute(
            "INSERT INTO casino_log (guild_id, user_id, game, bet, returned, detail, ts) VALUES (?, ?, 'duel', ?, ?, ?, ?)",
            (gid, uid, wagered, returned, detail[:40], time.time()),
        )
        await self.db.execute(
            "DELETE FROM casino_log WHERE guild_id = ? AND user_id = ? AND id NOT IN "
            "(SELECT id FROM casino_log WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 200)",
            (gid, uid, gid, uid),
        )
        await self.db.execute(
            "INSERT INTO casino_stats (guild_id, user_id, game, played, wagered, returned, best) VALUES (?, ?, 'duel', 1, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, game) DO UPDATE SET played = played + 1, wagered = wagered + excluded.wagered, "
            "returned = returned + excluded.returned, best = MAX(best, excluded.best)",
            (gid, uid, wagered, returned, max(0, returned - wagered)),
        )

    async def listing(self, gid: int, uid: int) -> dict:
        def card(r):
            return {
                "id": r["id"], "challenger_id": str(r["challenger_id"]), "challenger": r["challenger_name"],
                "opponent_id": str(r["opponent_id"]), "opponent": r["opponent_name"], "bet": r["bet"], "side": r["side"],
                "status": r["status"], "result": r["result"], "winner_id": str(r["winner_id"]) if r["winner_id"] else None,
                "expires": r["expires"], "resolved": r["resolved"],
            }
        now = time.time()
        inc = await self.db.fetchall(
            "SELECT * FROM coin_duels WHERE guild_id = ? AND opponent_id = ? AND status = 'pending' AND expires > ? ORDER BY id DESC", (gid, uid, now)
        )
        out = await self.db.fetchall(
            "SELECT * FROM coin_duels WHERE guild_id = ? AND challenger_id = ? AND status = 'pending' AND expires > ? ORDER BY id DESC", (gid, uid, now)
        )
        rec = await self.db.fetchall(
            "SELECT * FROM coin_duels WHERE guild_id = ? AND (challenger_id = ? OR opponent_id = ?) AND status NOT IN ('pending', 'resolving') "
            "ORDER BY resolved DESC LIMIT 10", (gid, uid, uid),
        )
        return {"incoming": [card(r) for r in inc], "outgoing": [card(r) for r in out], "recent": [card(r) for r in rec], "ttl": DUEL_TTL}

    # ------------------------------------------------------------------
    # Comando de Discord
    # ------------------------------------------------------------------
    caracruz = app_commands.Group(name="caracruz", description="Cara o cruz contra otra persona", guild_only=True)

    @caracruz.command(name="duelo", description="Desafiá a alguien a cara o cruz: el ganador se lleva todo")
    @app_commands.describe(usuario="A quién desafiás", monto=f"Monedas que apostás cada uno (mínimo {MIN_BET})", lado="El lado que elegís (el otro se queda con el contrario)")
    @app_commands.choices(lado=[app_commands.Choice(name="Cara", value="cara"), app_commands.Choice(name="Cruz", value="cruz")])
    async def duelo(self, interaction: discord.Interaction, usuario: discord.Member, monto: app_commands.Range[int, MIN_BET, MAX_BET], lado: app_commands.Choice[str]):
        try:
            row = await self.create(interaction.guild, interaction.user, usuario, monto, lado.value, source="discord")
        except DuelError as e:
            return await interaction.response.send_message(embed=error(e.message), ephemeral=True)
        view = DuelView(self, row["id"], row["challenger_id"], row["opponent_id"])
        try:
            await interaction.response.send_message(
                content=usuario.mention, embed=self.pending_embed(row), view=view,
                allowed_mentions=discord.AllowedMentions(users=[usuario]),
            )
            self.msgs[row["id"]] = await interaction.original_response()
        except discord.HTTPException:
            await self._close(row["id"], interaction.user.id, "cancelled")


async def setup(bot: commands.Bot):
    await bot.add_cog(Duels(bot))
