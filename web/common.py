"""Piezas compartidas del panel web que no dependen de aiohttp ni de Discord."""
import base64
import hashlib
import hmac
import json
import time


class ApiError(Exception):
    """Error con mensaje listo para mostrarle a la persona (y el código HTTP que corresponde)."""

    def __init__(self, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


# El panel no carga nada de afuera salvo las tipografías de Google y los avatares de Discord.
CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https://cdn.discordapp.com; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "script-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}

SESSION_COOKIE = "dilus_session"
SESSION_DAYS = 3


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict, secret: bytes) -> str:
    """Cookie firmada (HMAC-SHA256): no se puede alterar sin conocer el secreto."""
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    mac = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def unsign(token: str | None, secret: bytes) -> dict | None:
    if not token or token.count(".") != 1:
        return None
    try:
        body, mac = token.split(".")
        expected = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(mac, expected):
            return None
        data = json.loads(_unb64(body))
        if not isinstance(data, dict) or data.get("e", 0) < time.time():
            return None
        return data
    except Exception:
        return None
