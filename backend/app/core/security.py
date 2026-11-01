"""Password hashing and login tokens.

Passwords: PBKDF2-HMAC-SHA256 with a random 16-byte salt and 600,000
iterations (OWASP 2023 guidance), from Python's standard library. The stored
string records the algorithm and iteration count, so the cost can be raised
later without breaking existing passwords. The plain password is never stored.

Tokens: JSON Web Tokens signed with HS256. The token carries the user id
("sub"), role and expiry time ("exp"); the signature stops anyone changing
them. Every request still reloads the user, so deactivating an account or
changing a role takes effect immediately.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import jwt

from app.core.config import get_settings

logger = logging.getLogger("app.security")

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 10


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash."""
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Used when the email does not exist, so a failed login takes the same time
# whether or not the account exists (prevents discovering valid emails).
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


@lru_cache
def jwt_secret() -> str:
    configured = get_settings().jwt_secret_key
    if configured:
        return configured
    logger.warning("JWT_SECRET_KEY is not set; using a temporary random key (tokens end at restart).")
    return secrets.token_urlsafe(48)


def create_access_token(user_id: int, role: str, expires_minutes: int | None = None) -> tuple[str, int]:
    """Return (token, lifetime in seconds)."""
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, jwt_secret(), algorithm=settings.jwt_algorithm), minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    """Return the token's claims; raises jwt.InvalidTokenError if forged, malformed or expired."""
    return jwt.decode(token, jwt_secret(), algorithms=[get_settings().jwt_algorithm],
                      options={"require": ["sub", "exp"]})
