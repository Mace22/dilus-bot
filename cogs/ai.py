import asyncio
import logging
import os
import time
from collections import deque

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import BRAND_COLOR, error

log = logging.getLogger("dilus-bot.ai")

# ---------------------------------------------------------------------------
# Configuración (casi todo se cambia con variables de entorno, sin tocar código)
#   GEMINI_API_KEY        -> tu API key de https://aistudio.google.com/apikey  (obligatoria)
#   GEMINI_MODEL          -> modelo a usar (por defecto el de abajo)
#   GEMINI_MAX_TOKENS     -> largo máximo de cada respuesta
#   GEMINI_SYSTEM_PROMPT  -> personalidad del bot (opcional)
# ---------------------------------------------------------------------------
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.8-flash"
HISTORY_TURNS = 6          # cuántos intercambios recuerda por persona
HISTORY_TTL = 30 * 60      # olvida la charla tras 30 min sin hablar
DEFAULT_SYSTEM_PROMPT = (
    "Sos Dilu's Bot, un asistente de un servidor de Discord: simpático, directo y con buena onda. "
    "Respondé en español rioplatense (voseo) salvo que te pidan otro idioma. "
    "Sé breve y claro (idealmente menos de 1500 caracteres) y podés usar el formato de Discord "
    "(**negrita**, listas, `código`). Si no sabés algo, decilo en vez de inventar."
)
TRANSLATE_PROMPT = "Sos un traductor profesional. Devolvé ÚNICAMENTE la traducción, sin explicaciones ni comillas."

NO_PINGS = discord.AllowedMentions.none()


class GeminiError(Exception):
    """Error con un mensaje listo para mostrarle a la persona."""


def chunk_text(text: str, size: int = 3900) -> list[str]:
    chunks = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        chunks.append(text[:cut].strip())
        text = text[cut:].lstrip()
    if text.strip():
        chunks.append(text.strip())
    return chunks or ["(sin respuesta)"]


def extract_text(data) -> str:
    """Saca el texto de la respuesta de Gemini (ignora los 'pensamientos' internos)."""
    if not isinstance(data, dict):
        raise GeminiError("Gemini devolvió una respuesta rara. Probá de nuevo.")
    candidates = data.get("candidates") or []
    if not candidates:
        if (data.get("promptFeedback") or {}).get("blockReason"):
            raise GeminiError("Gemini bloqueó ese pedido por sus filtros de seguridad.")
        raise GeminiError("Gemini no devolvió respuesta. Probá de nuevo.")
    cand = candidates[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    if text.strip():
        return text.strip()
    reason = cand.get("finishReason")
    if reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
        raise GeminiError("Gemini bloqueó esa respuesta por sus filtros de seguridad.")
    if reason == "MAX_TOKENS":
        raise GeminiError("La respuesta se quedó sin espacio. Probá con una pregunta más corta.")
    raise GeminiError("Gemini no devolvió texto. Probá de nuevo.")


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
        self.system_prompt = os.getenv("GEMINI_SYSTEM_PROMPT", "").strip() or DEFAULT_SYSTEM_PROMPT
        try:
            self.max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "2048"))
        except ValueError:
            self.max_tokens = 2048
        self.session: aiohttp.ClientSession | None = None
        self._history: dict[tuple[int, int], tuple[float, deque]] = {}
        self._busy: set[tuple[int, int]] = set()
        self._mention_cd: dict[int, float] = {}

    async def cog_load(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        if not self.api_key:
            log.warning("GEMINI_API_KEY no está configurada: los comandos de IA van a avisar que falta la clave.")
        else:
            log.info("IA lista (modelo: %s)", self.model)

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    # ------------------------------------------------------------------
    # Llamada a Gemini
    # ------------------------------------------------------------------
    async def generate(self, contents: list[dict], system: str | None = None) -> str:
        if not self.api_key:
            raise GeminiError("La IA no está configurada todavía (falta `GEMINI_API_KEY` en el hosting).")

        url = f"{API_BASE}/{self.model}:generateContent"
        body = {
            "system_instruction": {"parts": [{"text": system or self.system_prompt}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": self.max_tokens},
        }
        try:
            async with self.session.post(url, json=body, headers={"x-goog-api-key": self.api_key}) as resp:
                status = resp.status
                try:
                    data = await resp.json(content_type=None)
                except ValueError:
                    data = {}
        except asyncio.TimeoutError:
            raise GeminiError("Gemini tardó demasiado en responder. Probá de nuevo.")
        except aiohttp.ClientError:
            raise GeminiError("No pude conectarme con Gemini. Probá de nuevo en un rato.")

        if status != 200:
            detail = ""
            if isinstance(data, dict):
                detail = str((data.get("error") or {}).get("message", ""))
            log.warning("Gemini respondió HTTP %s (modelo %s): %s", status, self.model, detail[:300])
            if status in (401, 403) or (status == 400 and "api key" in detail.lower()):
                raise GeminiError("La API key de Gemini no es válida o no tiene permiso.")
            if status == 404:
                raise GeminiError(f"El modelo `{self.model}` no existe o ya no está disponible. Cambiá `GEMINI_MODEL`.")
            if status == 429:
                raise GeminiError("Se alcanzó el límite de uso de Gemini. Esperá un momento y probá de nuevo.")
            if status >= 500:
                raise GeminiError("Gemini está con problemas ahora mismo. Probá más tarde.")
            raise GeminiError("Gemini rechazó el pedido.")

        return extract_text(data)

    def _get_history(self, key: tuple[int, int]) -> deque:
        entry = self._history.get(key)
        now = time.time()
        if entry is None or now - entry[0] > HISTORY_TTL:
            entry = (now, deque(maxlen=HISTORY_TURNS * 2))
        self._history[key] = (now, entry[1])
        return entry[1]

    async def chat(self, guild_id: int, user_id: int, prompt: str) -> str:
        """Conversa con memoria corta por persona."""
        history = self._get_history((guild_id, user_id))
        contents = [{"role": role, "parts": [{"text": text}]} for role, text in history]
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        answer = await self.generate(contents)
        history.append(("user", prompt[:1500]))
        history.append(("model", answer[:1500]))
        return answer

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------
    @app_commands.command(name="ask", description="🤖 Preguntale lo que quieras a la IA (Gemini)")
    @app_commands.describe(pregunta="Tu pregunta o pedido")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 8.0, key=lambda i: (i.guild_id, i.user.id))
    async def ask(self, interaction: discord.Interaction, pregunta: app_commands.Range[str, 1, 1500]):
        key = (interaction.guild_id, interaction.user.id)
        if key in self._busy:
            return await interaction.response.send_message(embed=error("Todavía estoy pensando tu pregunta anterior."), ephemeral=True)
        await interaction.response.defer()
        self._busy.add(key)
        try:
            answer = await self.chat(interaction.guild_id, interaction.user.id, pregunta)
        except GeminiError as e:
            return await interaction.followup.send(embed=error(str(e)))
        finally:
            self._busy.discard(key)

        chunks = chunk_text(answer)
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(description=chunk, color=BRAND_COLOR)
            if i == 0:
                embed.title = ("💬 " + pregunta)[:250]
                embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.set_footer(text="Dilu's Bot • Gemini" + (f" • {i + 1}/{len(chunks)}" if len(chunks) > 1 else ""))
            await interaction.followup.send(embed=embed, allowed_mentions=NO_PINGS)

    @app_commands.command(name="olvidar", description="Borra la memoria de tu charla con la IA y empieza de cero")
    @app_commands.guild_only()
    async def olvidar(self, interaction: discord.Interaction):
        self._history.pop((interaction.guild_id, interaction.user.id), None)
        await interaction.response.send_message("🧹 Listo, empezamos una charla nueva.", ephemeral=True)

    @app_commands.command(name="traducir", description="🌐 Traduce un texto a otro idioma con la IA")
    @app_commands.describe(texto="Texto a traducir", idioma="Idioma destino (ej: inglés, portugués, japonés)")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 8.0, key=lambda i: (i.guild_id, i.user.id))
    async def traducir(self, interaction: discord.Interaction, texto: app_commands.Range[str, 1, 1500], idioma: app_commands.Range[str, 2, 40]):
        await interaction.response.defer()
        prompt = f"Traducí el siguiente texto a {idioma}:\n\n{texto}"
        try:
            result = await self.generate([{"role": "user", "parts": [{"text": prompt}]}], system=TRANSLATE_PROMPT)
        except GeminiError as e:
            return await interaction.followup.send(embed=error(str(e)))
        embed = discord.Embed(title=f"🌐 Traducción ({idioma})", description=result[:4000], color=BRAND_COLOR)
        embed.set_footer(text="Dilu's Bot • Gemini")
        await interaction.followup.send(embed=embed, allowed_mentions=NO_PINGS)

    # ------------------------------------------------------------------
    # Charlar mencionando al bot: "@Dilu's Bot hola"
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not self.api_key:
            return
        if self.bot.user not in message.mentions:
            return
        content = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
        if not content:
            return

        now = time.time()
        if now - self._mention_cd.get(message.author.id, 0) < 6:
            return
        key = (message.guild.id, message.author.id)
        if key in self._busy:
            return
        self._mention_cd[message.author.id] = now
        self._busy.add(key)
        try:
            async with message.channel.typing():
                answer = await self.chat(message.guild.id, message.author.id, content[:1500])
        except GeminiError as e:
            await message.reply(f"❌ {e}", mention_author=False, allowed_mentions=NO_PINGS)
            return
        finally:
            self._busy.discard(key)

        for i, chunk in enumerate(chunk_text(answer, 1900)):
            try:
                if i == 0:
                    await message.reply(chunk, mention_author=False, allowed_mentions=NO_PINGS)
                else:
                    await message.channel.send(chunk, allowed_mentions=NO_PINGS)
            except discord.HTTPException:
                break


async def setup(bot: commands.Bot):
    await bot.add_cog(AI(bot))
