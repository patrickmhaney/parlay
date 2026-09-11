"""Magic-link authentication.

No passwords anywhere. A login link is a single-use, short-lived random token;
only its SHA-256 hash is ever stored, so a database leak cannot be replayed
into a login. Sessions last 120 days by default.

Invites use the identical token machinery, which is why there is one flow to
get right instead of two.
"""
from __future__ import annotations

import hashlib
import secrets
from urllib.parse import urlencode

from fastapi import Request

from app.config import get_settings
from app.db import Database, get_db
from app.repositories import users as repo

TOKEN_BYTES = 32


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- login -----------------------------------------------------------------


def issue_login_link(db: Database, email: str, redirect_to: str | None = None) -> str:
    settings = get_settings()
    token = new_token()
    repo.create_login_token(
        db, hash_token(token), email, settings.login_token_minutes, redirect_to
    )
    q = urlencode({"token": token})
    return f"{settings.base_url.rstrip('/')}/auth/verify?{q}"


def revoke_login_link(db: Database, link: str) -> None:
    """Remove a link that was never delivered, so it can't be used and
    doesn't count toward the per-address rate limit."""
    from urllib.parse import parse_qs, urlparse
    token = (parse_qs(urlparse(link).query).get("token") or [""])[0]
    if token:
        db.execute("DELETE FROM login_tokens WHERE token_hash = ?", [hash_token(token)])


def recent_login_requests(db: Database, email: str, minutes: int = 15) -> int:
    """How many sign-in links this address has been sent recently."""
    from datetime import timedelta
    since = repo.now() - timedelta(minutes=minutes)
    return int(db.value(
        "SELECT COUNT(*) FROM login_tokens WHERE email = ? AND created_at > ?",
        [email.strip().lower(), since],
    ) or 0)


def redeem_login_token(db: Database, token: str) -> tuple[dict, str, str | None] | None:
    """Returns (user, session_token, redirect_to), or None if the link is
    bad, already used, or expired."""
    row = repo.consume_login_token(db, hash_token(token))
    if not row:
        return None
    user = repo.get_or_create_user(db, row["email"])
    session_token = new_token()
    repo.create_session(
        db, hash_token(session_token), user["id"], get_settings().session_days
    )
    repo.touch_login(db, user["id"])
    return user, session_token, row.get("redirect_to")


def logout(db: Database, session_token: str) -> None:
    repo.delete_session(db, hash_token(session_token))


# --- invites ---------------------------------------------------------------


def issue_invite_link(
    db: Database, syndicate_id: str, email: str | None, invited_by: str | None
) -> str:
    settings = get_settings()
    token = new_token()
    repo.create_invite(
        db, syndicate_id, hash_token(token), email, invited_by,
        settings.invite_token_days,
    )
    return f"{settings.base_url.rstrip('/')}/invite/{token}"


def lookup_invite(db: Database, token: str) -> dict | None:
    inv = repo.get_invite(db, hash_token(token))
    if not inv:
        return None
    if inv["accepted_at"] is not None:
        return None
    if inv["expires_at"] < repo.now():
        return None
    return inv


# --- request helpers -------------------------------------------------------


def current_user(request: Request) -> dict | None:
    """Cached on request.state so a template and its route don't double-query."""
    cached = getattr(request.state, "_user", "unset")
    if cached != "unset":
        return cached
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie)
    user = None
    if token:
        db = get_db()
        user = repo.session_user(db, hash_token(token))
        if user:
            repo.touch_session(db, hash_token(token))
    request.state._user = user
    return user


def set_session_cookie(response, session_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie,
        session_token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(get_settings().session_cookie, path="/")
