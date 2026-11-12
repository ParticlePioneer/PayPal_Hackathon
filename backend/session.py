"""Server-signed browser sessions for the integrated negotiation and checkout."""
import hashlib
import hmac
import os
import re
import secrets

COOKIE = "agent_session"
_TOKEN = re.compile(r"^([0-9a-f]{64})\.([0-9a-f]{64})$")


def sign(nonce: str, secret: str) -> str:
    signature = hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    return nonce + "." + signature


def session_for_cookie(cookie: str, secret: str) -> str | None:
    match = _TOKEN.fullmatch(cookie or "")
    if not match or not hmac.compare_digest(sign(match.group(1), secret), cookie):
        return None
    return "s_" + hashlib.sha256(match.group(1).encode()).hexdigest()


def new_cookie(secret: str) -> str:
    return sign(secrets.token_hex(32), secret)


def configured_secret() -> str:
    secret = os.getenv("SESSION_SECRET", "")
    if len(secret) < 32 or secret == "replace-with-a-long-random-secret":
        raise RuntimeError("SESSION_SECRET must be a configured random secret of at least 32 characters")
    return secret
