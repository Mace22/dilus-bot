import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import error, make_embed, ok

# ---------- Configuración (tocá estos valores a gusto) ----------
COIN = "🪙"
DAILY_BASE = 200            # monedas del /daily
DAILY_STREAK_BONUS = 25     # extra por cada día seguido
DAILY_STREAK_CAP = 10       # tope de días para el bonus
WORK_RANGE = (50, 150)      # monedas por /trabajar
WORK_COOLDOWN = 3600        # segundos entre /trabajar
CHAT_COINS = (1, 3)         # monedas por mensaje (con cooldown)
CHAT_COOLDOWN = 60
MIN_BET, MAX_BET = 10, 5000
# -----------------------------------------------------------------

JOBS = [
    "atendiste un kiosco 24 horas",
    "repartiste pedidos en bici",
    "arreglaste la compu de un vecino",
    "cuidaste perros en la plaza",
    "diseñaste un logo para un amigo",
    "lavaste autos en la cuadra",
    "hiciste de DJ en un cumpleaños",
    "vendiste empanadas en la facultad",
]

SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
SLOT_MULT = {"🍒": 3, "🍋": 4, "🔔": 5, "💎": 8, "7️⃣": 15}
SLOT_PAIR_MULT = 1.4


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._chat_cd: dict[tuple[int, int], float] = {}

    # ------------------------------------------------------------------
    # Helpers de base de datos (las operaciones son atómicas: no se puede quedar en negativo)
    # ------------------------------------------------------------------
    async def _ensure(self, gid: int, uid: int):
        await self.bot.db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)", (gid, uid))

    async def get_row(self, gid: int, uid: int):
        await self._ensure(gid, uid)
        return await self.bot.db.fetchone("SELECT * FROM economy WHERE guild_id = ? AND user_id = ?", (gid, uid))

    async def balance(self, gid: int, uid: int) -> int:
        return (await self.get_row(gid, uid))["balance"]

    async def add(self, gid: int, uid: int, delta: int) -> bool:
        """Suma/resta monedas. Devuelve False si no alcanza el saldo."""
        await self._ensure(gid, uid)
        cur = await self.bot.db.execute(
            "UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ? AND balance + ? >= 0",
            (delta, gid, uid, delta),
        )
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Monedas por chatear
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        key = (message.guild.id, message.author.id)
        now = time.time()
        if now - self._chat_cd.get(key, 0) < CHAT_COOLDOWN:
            return
        self._chat_cd[key] = now
        await self.add(message.guild.id, message.author.id, random.randint(*CHAT_COINS))

    # ------------------------------------------------------------------
    # Comandos básicos
    # ------------------------------------------------------------------
    @app_commands.command(name="balance", description="Mirá tus monedas (o las de otra persona)")
    @app_commands.guild_only()
    async def balance_cmd(self, interaction: discord.Interaction, miembro: discord.Member | None = None):
        member = miembro or interaction.user
        bal = await self.balance(interaction.guild_id, member.id)
        pos = await self.bot.db.fetchone(
            "SELECT COUNT(*) + 1 AS pos FROM economy WHERE guild_id = ? AND balance > ?", (interaction.guild_id, bal)
        )
        embed = make_embed(f"{COIN} Billetera de {member.display_name}")
        embed.add_field(name="Monedas", value=f"**{fmt(bal)}** {COIN}")
        embed.add_field(name="Puesto", value=f"#{pos['pos']}")
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description="Reclamá tu recompensa diaria (¡con bonus por días seguidos!)")
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction):
        gid, uid = interaction.guild_id, interaction.user.id
        row = await self.get_row(gid, uid)
        now = time.time()
        last = row["last_daily"]

        if now - last < 86400:
            return await interaction.response.send_message(
                embed=error(f"Ya reclamaste tu diaria. Volvé <t:{int(last + 86400)}:R>."), ephemeral=True
            )

        streak = row["streak"] + 1 if 0 < last and now - last < 172800 else 1
        reward = DAILY_BASE + min(streak - 1, DAILY_STREAK_CAP) * DAILY_STREAK_BONUS
        cur = await self.bot.db.execute(
            "UPDATE economy SET balance = balance + ?, last_daily = ?, streak = ? "
            "WHERE guild_id = ? AND user_id = ? AND last_daily = ?",
            (reward, now, streak, gid, uid, last),
        )
        if cur.rowcount == 0:
            return await interaction.response.send_message(embed=error("Ya reclamaste tu diaria."), ephemeral=True)
        await interaction.response.send_message(
            embed=ok(f"Recibiste **{fmt(reward)}** {COIN}  •  Racha: **{streak}** día(s) 🔥")
        )

    @app_commands.command(name="trabajar", description="Trabajá un rato para ganar monedas")
    @app_commands.guild_only()
    async def trabajar(self, interaction: discord.Interaction):
        gid, uid = interaction.guild_id, interaction.user.id
        row = await self.get_row(gid, uid)
        now = time.time()
        last = row["last_work"]
        if now - last < WORK_COOLDOWN:
            return await interaction.response.send_message(
                embed=error(f"Estás cansado. Podés volver a trabajar <t:{int(last + WORK_COOLDOWN)}:R>."), ephemeral=True
            )
        reward = random.randint(*WORK_RANGE)
        cur = await self.bot.db.execute(
            "UPDATE economy SET balance = balance + ?, last_work = ? WHERE guild_id = ? AND user_id = ? AND last_work = ?",
            (reward, now, gid, uid, last),
        )
        if cur.rowcount == 0:
            return await interaction.response.send_message(embed=error("Ya estás trabajando."), ephemeral=True)
        await interaction.response.send_message(embed=ok(f"{random.choice(JOBS).capitalize()} y ganaste **{fmt(reward)}** {COIN}"))

    @app_commands.command(name="pay", description="Mandale monedas a otra persona")
    @app_commands.guild_only()
    async def pay(self, interaction: discord.Interaction, miembro: discord.Member, monto: app_commands.Range[int, 1, 1_000_000]):
        if miembro.bot or miembro.id == interaction.user.id:
            return await interaction.response.send_message(embed=error("Elegí a otra persona (no bots ni vos mismo)."), ephemeral=True)
        gid = interaction.guild_id
        if not await self.add(gid, interaction.user.id, -monto):
            return await interaction.response.send_message(embed=error("No tenés suficientes monedas."), ephemeral=True)
        await self.add(gid, miembro.id, monto)
        await interaction.response.send_message(
            embed=ok(f"Le mandaste **{fmt(monto)}** {COIN} a {miembro.mention}."),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="ricos", description="Ranking de las personas con más monedas")
    @app_commands.guild_only()
    async def ricos(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT user_id, balance FROM economy WHERE guild_id = ? AND balance > 0 ORDER BY balance DESC LIMIT 10",
            (interaction.guild_id,),
        )
        if not rows:
            return await interaction.response.send_message(embed=error("Todavía no hay nadie con monedas."))
        medals = ["🥇", "🥈", "🥉"]
        lines = [
            f"{medals[i] if i < 3 else f'`{i + 1}.`'} <@{r['user_id']}> — **{fmt(r['balance'])}** {COIN}"
            for i, r in enumerate(rows)
        ]
        await interaction.response.send_message(
            embed=make_embed(f"{COIN} Los más ricos", "\n".join(lines)), allowed_mentions=discord.AllowedMentions.none()
        )

    # ------------------------------------------------------------------
    # Juegos
    # ------------------------------------------------------------------
    @app_commands.command(name="apostar", description="Cara o cruz: si acertás, duplicás lo apostado")
    @app_commands.choices(
        lado=[app_commands.Choice(name="Cara", value="cara"), app_commands.Choice(name="Cruz", value="cruz")]
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 4.0, key=lambda i: (i.guild_id, i.user.id))
    async def apostar(self, interaction: discord.Interaction, monto: app_commands.Range[int, MIN_BET, MAX_BET], lado: app_commands.Choice[str]):
        gid, uid = interaction.guild_id, interaction.user.id
        if not await self.add(gid, uid, -monto):
            return await interaction.response.send_message(embed=error("No tenés suficientes monedas."), ephemeral=True)
        result = random.choice(["cara", "cruz"])
        if result == lado.value:
            await self.add(gid, uid, monto * 2)
            msg = f"Salió **{result}** y ganaste **{fmt(monto)}** {COIN} 🎉"
            await interaction.response.send_message(embed=ok(msg))
        else:
            await interaction.response.send_message(
                embed=make_embed(description=f"Salió **{result}**... perdiste **{fmt(monto)}** {COIN} 💸", color=0xEF4444)
            )

    @app_commands.command(name="slots", description="Tragamonedas: ¡tres iguales pagan un montón!")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 4.0, key=lambda i: (i.guild_id, i.user.id))
    async def slots(self, interaction: discord.Interaction, monto: app_commands.Range[int, MIN_BET, MAX_BET]):
        gid, uid = interaction.guild_id, interaction.user.id
        if not await self.add(gid, uid, -monto):
            return await interaction.response.send_message(embed=error("No tenés suficientes monedas."), ephemeral=True)

        reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        board = f"**[ {' | '.join(reels)} ]**"
        if len(set(reels)) == 1:
            payout, text, color = monto * SLOT_MULT[reels[0]], "¡JACKPOT!", 0xF59E0B
        elif len(set(reels)) == 2:
            payout, text, color = int(monto * SLOT_PAIR_MULT), "Dos iguales", 0x22C55E
        else:
            payout, text, color = 0, "Nada esta vez", 0xEF4444

        if payout:
            await self.add(gid, uid, payout)
        net = payout - monto
        sign = "+" if net >= 0 else "−"
        embed = make_embed(
            f"🎰 {text}",
            f"{board}\n\nResultado: **{sign}{fmt(abs(net))}** {COIN}",
            color=color,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Tienda de roles
    # ------------------------------------------------------------------
    @app_commands.command(name="tienda", description="Roles que podés comprar con monedas")
    @app_commands.guild_only()
    async def tienda(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT role_id, price FROM shop WHERE guild_id = ? ORDER BY price", (interaction.guild_id,)
        )
        lines = [f"<@&{r['role_id']}> — **{fmt(r['price'])}** {COIN}" for r in rows if interaction.guild.get_role(r["role_id"])]
        if not lines:
            return await interaction.response.send_message(embed=error("La tienda está vacía por ahora."))
        embed = make_embed("🛒 Tienda de roles", "\n".join(lines) + "\n\nComprá con `/comprar`.")
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="comprar", description="Comprá un rol de la tienda")
    @app_commands.guild_only()
    async def comprar(self, interaction: discord.Interaction, rol: discord.Role):
        gid = interaction.guild_id
        item = await self.bot.db.fetchone("SELECT price FROM shop WHERE guild_id = ? AND role_id = ?", (gid, rol.id))
        if not item:
            return await interaction.response.send_message(embed=error("Ese rol no está en la tienda."), ephemeral=True)
        if rol in interaction.user.roles:
            return await interaction.response.send_message(embed=error("Ya tenés ese rol."), ephemeral=True)
        if rol >= interaction.guild.me.top_role:
            return await interaction.response.send_message(embed=error("No puedo darte ese rol (está por encima del mío)."), ephemeral=True)
        if not await self.add(gid, interaction.user.id, -item["price"]):
            return await interaction.response.send_message(embed=error("No tenés suficientes monedas."), ephemeral=True)
        try:
            await interaction.user.add_roles(rol, reason="Compra en la tienda - Dilu's Bot")
        except discord.HTTPException:
            await self.add(gid, interaction.user.id, item["price"])  # devolución
            return await interaction.response.send_message(embed=error("No pude darte el rol. No se cobró nada."), ephemeral=True)
        await interaction.response.send_message(
            embed=ok(f"Compraste {rol.mention} por **{fmt(item['price'])}** {COIN}."),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ------------------------------------------------------------------
    # Administración
    # ------------------------------------------------------------------
    economia = app_commands.Group(
        name="economia",
        description="Administrar la economía del servidor",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @economia.command(name="dar", description="Suma monedas a un miembro (número negativo para restar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def eco_dar(self, interaction: discord.Interaction, miembro: discord.Member, cantidad: int):
        if not await self.add(interaction.guild_id, miembro.id, cantidad):
            return await interaction.response.send_message(embed=error("Esa persona no tiene tantas monedas para restar."), ephemeral=True)
        await interaction.response.send_message(
            embed=ok(f"{miembro.mention}: {cantidad:+d} {COIN}"), allowed_mentions=discord.AllowedMentions.none()
        )

    @economia.command(name="tienda_agregar", description="Agrega (o cambia el precio de) un rol en la tienda")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shop_add(self, interaction: discord.Interaction, rol: discord.Role, precio: app_commands.Range[int, 1, 10_000_000]):
        if rol >= interaction.guild.me.top_role or rol.is_default() or rol.managed:
            return await interaction.response.send_message(
                embed=error("No puedo asignar ese rol (está por encima del mío o es un rol especial)."), ephemeral=True
            )
        await self.bot.db.execute(
            "INSERT INTO shop (guild_id, role_id, price) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, role_id) DO UPDATE SET price = excluded.price",
            (interaction.guild_id, rol.id, precio),
        )
        await interaction.response.send_message(
            embed=ok(f"{rol.mention} ahora se vende a **{fmt(precio)}** {COIN}."),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @economia.command(name="tienda_quitar", description="Saca un rol de la tienda")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shop_remove(self, interaction: discord.Interaction, rol: discord.Role):
        await self.bot.db.execute("DELETE FROM shop WHERE guild_id = ? AND role_id = ?", (interaction.guild_id, rol.id))
        await interaction.response.send_message(embed=ok(f"Saqué {rol.mention} de la tienda."), allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
