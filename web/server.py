"""Servidor web (aiohttp): login con Discord, sesión por cookie firmada, API y archivos del panel."""
import json
import logging
import os
import secrets
import time
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout, web

from web.api import Api
from web.common import SECURITY_HEADERS, SESSION_COOKIE, SESSION_DAYS, ApiError, sign, unsign

log = logging.getLogger("dilus-bot.web")

DISCORD_API = "https://discord.com/api/v10"
STATE_COOKIE = "dilus_state"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
USER_AGENT = "DiscordBot (https://github.com/Mace22/dilus-bot, 1.0)"


class WebServer:
    def __init__(self, bot, services, *, base_url: str, host: str, port: int, client_secret: str, session_secret: bytes):
        self.bot = bot
        self.api = Api(bot, services)
        self.base_url = base_url.rstrip("/")
        self.host, self.port = host, port
        self.client_secret = client_secret
        self.secret = session_secret
        self.secure = self.base_url.startswith("https://")
        self.redirect_uri = f"{self.base_url}/auth/callback"
        self.runner: web.AppRunner | None = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def start(self):
        app = web.Application(middlewares=[self.security_middleware], client_max_size=64 * 1024)
        app.router.add_get("/", self.index)
        app.router.add_get("/auth/login", self.login)
        app.router.add_get("/auth/callback", self.callback)
        app.router.add_post("/auth/logout", self.logout)
        app.router.add_route("*", "/api/{tail:.*}", self.api_handler)
        app.router.add_static("/static/", STATIC_DIR, follow_symlinks=False)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, self.host, self.port).start()
        log.info("Panel web escuchando en %s:%s (URL pública: %s)", self.host, self.port, self.base_url)

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    # ------------------------------------------------------------------
    # Middleware: cabeceras de seguridad y errores en JSON
    # ------------------------------------------------------------------
    @web.middleware
    async def security_middleware(self, request: web.Request, handler):
        try:
            response = await handler(request)
        except web.HTTPException as exc:           # redirecciones, 404 de archivos, etc.
            response = exc
        except ApiError as exc:
            response = web.json_response({"error": exc.message, **exc.extra}, status=exc.status)
        except Exception:
            log.exception("Error en %s %s", request.method, request.path)
            response = web.json_response({"error": "Ocurrió un error inesperado. Probá de nuevo."}, status=500)
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        if request.path.startswith(("/api/", "/auth/")):
            response.headers["Cache-Control"] = "no-store"
        elif request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        if isinstance(response, web.HTTPException):
            raise response
        return response

    # ------------------------------------------------------------------
    # Páginas
    # ------------------------------------------------------------------
    async def index(self, request: web.Request):
        return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))

    # ------------------------------------------------------------------
    # Sesión
    # ------------------------------------------------------------------
    def session(self, request: web.Request) -> dict | None:
        return unsign(request.cookies.get(SESSION_COOKIE), self.secret)

    def _cookie(self, response, name: str, value: str, max_age: int):
        response.set_cookie(name, value, max_age=max_age, httponly=True, secure=self.secure, samesite="Lax", path="/")

    # ------------------------------------------------------------------
    # Login con Discord (OAuth2: authorization code)
    # ------------------------------------------------------------------
    @property
    def client_id(self) -> str:
        return str(self.bot.application_id or self.bot.user.id)

    async def login(self, request: web.Request):
        state = secrets.token_urlsafe(24)
        params = urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": self.redirect_uri,
            "scope": "identify guilds", "state": state, "prompt": "none",
        })
        response = web.HTTPFound(f"https://discord.com/oauth2/authorize?{params}")
        self._cookie(response, STATE_COOKIE, state, 600)
        raise response

    async def callback(self, request: web.Request):
        expected = request.cookies.get(STATE_COOKIE)
        if request.query.get("error"):
            raise web.HTTPFound("/?error=denied")
        code, state = request.query.get("code"), request.query.get("state")
        if not code or not state or not expected or not secrets.compare_digest(state.encode(), expected.encode()):
            raise web.HTTPFound("/?error=state")
        try:
            user, guilds = await self._fetch_discord(code)
        except Exception:
            log.exception("Falló el login con Discord")
            raise web.HTTPFound("/?error=login")

        mutual = [str(g["id"]) for g in guilds if self.bot.get_guild(int(g["id"])) is not None][:80]
        payload = {
            "u": str(user["id"]),
            "n": user.get("global_name") or user.get("username") or "Usuario",
            "a": user.get("avatar"),
            "g": mutual,
            "e": time.time() + SESSION_DAYS * 86400,
        }
        response = web.HTTPFound("/")
        self._cookie(response, SESSION_COOKIE, sign(payload, self.secret), SESSION_DAYS * 86400)
        response.del_cookie(STATE_COOKIE, path="/")
        raise response

    async def _fetch_discord(self, code: str):
        data = {
            "client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "authorization_code",
            "code": code, "redirect_uri": self.redirect_uri,
        }
        async with ClientSession(timeout=ClientTimeout(total=15), headers={"User-Agent": USER_AGENT}) as http:
            async with http.post(f"{DISCORD_API}/oauth2/token", data=data) as r:
                if r.status != 200:
                    raise RuntimeError(f"Discord rechazó el código ({r.status}): {(await r.text())[:200]}")
                token = (await r.json())["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            async with http.get(f"{DISCORD_API}/users/@me", headers=headers) as r:
                r.raise_for_status()
                user = await r.json()
            async with http.get(f"{DISCORD_API}/users/@me/guilds", headers=headers) as r:
                r.raise_for_status()
                guilds = await r.json()
        return user, guilds

    async def logout(self, request: web.Request):
        self._check_csrf(request)
        response = web.json_response({"ok": True})
        response.del_cookie(SESSION_COOKIE, path="/")
        return response

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    @staticmethod
    def _check_csrf(request: web.Request):
        # Un sitio ajeno no puede mandar este encabezado sin permiso del navegador (CORS), así que frena el CSRF.
        if request.headers.get("X-Requested-With") != "fetch":
            raise ApiError("Pedido no permitido.", 403)

    async def api_handler(self, request: web.Request):
        body: dict = {}
        if request.method == "POST":
            self._check_csrf(request)
            try:
                body = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ApiError("El pedido no es válido.")
            if not isinstance(body, dict):
                raise ApiError("El pedido no es válido.")
        elif request.method != "GET":
            raise ApiError("Método no permitido.", 405)
        data = await self.api.handle(self.session(request), request.method, request.path, dict(request.query), body)
        return web.json_response(data)
