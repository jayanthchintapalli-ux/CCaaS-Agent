"""Authentication and role-based access control.

Passwords are salted + hashed with PBKDF2 (stdlib ``hashlib``). Sessions are
opaque bearer tokens stored in the ``tokens`` table. This is intentionally
lightweight — swap for your IdP / OAuth in production.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException

import db

_ITERATIONS = 120_000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _ITERATIONS
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _ITERATIONS
    ).hex()
    return hmac.compare_digest(check, digest)


def create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO tokens (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, now_iso()),
    )
    return token


def revoke_token(token: str) -> None:
    db.execute("DELETE FROM tokens WHERE token = ?", (token,))


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: resolve the bearer token to an active user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    row = db.query_one(
        """
        SELECT u.id, u.email, u.name, u.role, u.status
        FROM tokens t JOIN users u ON u.id = t.user_id
        WHERE t.token = ?
        """,
        (token,),
    )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="Account is disabled.")
    return row


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return user
