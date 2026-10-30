"""Rutas de la API del panel. No depende de aiohttp: recibe la sesión ya verificada y devuelve un dict."""
import time

from web.common import ApiError

# segundos mínimos entre dos llamadas de la misma persona a cada acción
THROTTLE = {
    "/api/roulette/spin": 1.0,
    "/api/blackjack/deal": 0.8,
    "/api/blackjack/action": 0.25,
    "/api/claim/daily": 1.0,
    "/api/claim/work": 1.0,
    "/api/shop/buy": 1.0,
}


def avatar_url(uid: str, avatar_hash: str | None) -> str:
    if avatar_hash:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.{ext}?size=128"
    return f"https://cdn.discordapp.com/embed/avatars/{(int(uid) >> 22) % 6}.png"


class Api:
    def __init__(self, bot, services):
        self.bot = bot
        self.svc = services
        self._last: dict[tuple[int, str], float] = {}
        self.routes = {
            ("GET", "/api/profile"): lambda g, u, q, b: self.svc.profile(g, u),
            ("POST", "/api/claim/daily"): lambda g, u, q, b: self.svc.claim_daily(g, u),
            ("POST", "/api/claim/work"): lambda g, u, q, b: self.svc.claim_work(g, u),
            ("GET", "/api/shop"): lambda g, u, q, b: self.svc.shop(g, u),
            ("POST", "/api/shop/buy"): lambda g, u, q, b: self.svc.buy(g, u, b.get("role")),
            ("GET", "/api/leaderboard"): lambda g, u, q, b: self.svc.leaderboard(g, u, q.get("type", "eco")),
            ("GET", "/api/blackjack"): lambda g, u, q, b: self.svc.bj_state(g, u),
            ("POST", "/api/blackjack/deal"): lambda g, u, q, b: self.svc.bj_deal(g, u, b.get("bet")),
            ("POST", "/api/blackjack/action"): lambda g, u, q, b: self.svc.bj_action(g, u, b.get("action")),
            ("GET", "/api/roulette/history"): lambda g, u, q, b: self.svc.roulette_history(g),
            ("POST", "/api/roulette/spin"): lambda g, u, q, b: self.svc.roulette_spin(g, u, b.get("bets")),
        }

    def throttle(self, uid: int, path: str):
        gap = THROTTLE.get(path, 0.4)
        now = time.monotonic()
        last = self._last.get((uid, path))
        if last is not None and now - last < gap:
            raise ApiError("Más despacio, probá de nuevo en un instante.", 429)
        self._last[(uid, path)] = now
        if len(self._last) > 5000:
            self._last.clear()

    def guild_id(self, session: dict, raw) -> int:
        text = str(raw) if raw is not None else ""
        if not text.isdigit() or text not in session.get("g", []):
            raise ApiError("No tenés acceso a ese servidor.", 403)
        gid = int(text)
        if self.bot.get_guild(gid) is None:
            raise ApiError("El bot ya no está en ese servidor.", 404)
        return gid

    async def handle(self, session: dict | None, method: str, path: str, query: dict, body: dict) -> dict:
        if path == "/api/session":
            if not session:
                return {"logged_in": False}
            return {
                "logged_in": True,
                "user": {"id": session["u"], "name": session["n"], "avatar": avatar_url(session["u"], session.get("a"))},
            }
        if not session:
            raise ApiError("Iniciá sesión con Discord.", 401)
        uid = int(session["u"])

        if path == "/api/guilds":
            cards = []
            for raw in session.get("g", []):
                guild = self.bot.get_guild(int(raw))
                if guild is not None:
                    cards.append(self.svc.guild_card(guild))
            return {"guilds": sorted(cards, key=lambda c: c["name"].lower())}

        route = self.routes.get((method, path))
        if route is None:
            raise ApiError("No existe.", 404)
        gid = self.guild_id(session, body.get("guild") if method == "POST" else query.get("guild"))
        if method == "POST":
            self.throttle(uid, path)
        return await route(gid, uid, query, body)
