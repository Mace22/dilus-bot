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
    "/api/tags/buy": 1.0,
    "/api/tags/equip": 1.0,
    "/api/admin/coins": 0.8,
    "/api/admin/mod": 0.8,
    "/api/slots/spin": 1.0,
    "/api/coinflip": 1.0,
    "/api/duel/create": 1.5,
    "/api/duel/accept": 0.8,
    "/api/duel/decline": 0.8,
    "/api/duel/cancel": 0.8,
    "/api/pay": 1.5,
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
            ("GET", "/api/tags"): lambda g, u, q, b: self.svc.tags(g, u),
            ("POST", "/api/tags/buy"): lambda g, u, q, b: self.svc.tag_buy(g, u, b.get("tag")),
            ("POST", "/api/tags/equip"): lambda g, u, q, b: self.svc.tag_equip(g, u, b.get("tag")),
            ("GET", "/api/admin/overview"): lambda g, u, q, b: self.svc.admin.overview(g, u),
            ("GET", "/api/admin/members"): lambda g, u, q, b: self.svc.admin.members(g, u, q.get("q")),
            ("GET", "/api/admin/logs"): lambda g, u, q, b: self.svc.admin.logs(g, u, q.get("kind")),
            ("POST", "/api/admin/coins"): lambda g, u, q, b: self.svc.admin.coins(g, u, b.get("target"), b.get("amount"), b.get("reason")),
            ("POST", "/api/admin/mod"): lambda g, u, q, b: self.svc.admin.moderate(g, u, b.get("action"), b.get("target"), b.get("reason"), b.get("minutes")),
            ("GET", "/api/leaderboard"): lambda g, u, q, b: self.svc.leaderboard(g, u, q.get("type", "eco")),
            ("GET", "/api/blackjack"): lambda g, u, q, b: self.svc.bj_state(g, u),
            ("POST", "/api/blackjack/deal"): lambda g, u, q, b: self.svc.bj_deal(g, u, b.get("bet")),
            ("POST", "/api/blackjack/action"): lambda g, u, q, b: self.svc.bj_action(g, u, b.get("action")),
            ("GET", "/api/roulette/history"): lambda g, u, q, b: self.svc.roulette_history(g),
            ("POST", "/api/roulette/spin"): lambda g, u, q, b: self.svc.roulette_spin(g, u, b.get("bets")),
            ("POST", "/api/slots/spin"): lambda g, u, q, b: self.svc.slots_spin(g, u, b.get("bet")),
            ("POST", "/api/coinflip"): lambda g, u, q, b: self.svc.coinflip(g, u, b.get("bet"), b.get("side")),
            ("GET", "/api/duel/list"): lambda g, u, q, b: self.svc.duel_list(g, u),
            ("POST", "/api/duel/create"): lambda g, u, q, b: self.svc.duel_create(g, u, b.get("target"), b.get("bet"), b.get("side")),
            ("POST", "/api/duel/accept"): lambda g, u, q, b: self.svc.duel_accept(g, u, b.get("id")),
            ("POST", "/api/duel/decline"): lambda g, u, q, b: self.svc.duel_decline(g, u, b.get("id")),
            ("POST", "/api/duel/cancel"): lambda g, u, q, b: self.svc.duel_cancel(g, u, b.get("id")),
            ("GET", "/api/activity"): lambda g, u, q, b: self.svc.activity(g, u),
            ("GET", "/api/achievements"): lambda g, u, q, b: self.svc.achievements(g, u),
            ("GET", "/api/members"): lambda g, u, q, b: self.svc.members(g, u, q.get("q")),
            ("POST", "/api/pay"): lambda g, u, q, b: self.svc.pay(g, u, b.get("target"), b.get("amount")),
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
