"""Users, syndicates, memberships, invites and sessions."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from app.db import Database


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return uuid.uuid4().hex


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "syndicate"


# --- users -----------------------------------------------------------------


def get_user(db: Database, user_id: str) -> dict | None:
    return db.row("SELECT * FROM users WHERE id = ?", [user_id])


def get_user_by_email(db: Database, email: str) -> dict | None:
    return db.row("SELECT * FROM users WHERE lower(email) = lower(?)", [email])


def create_user(
    db: Database, email: str, display_name: str, phone: str | None = None
) -> dict:
    uid = new_id()
    db.execute(
        "INSERT INTO users (id, email, display_name, phone, created_at) VALUES (?,?,?,?,?)",
        [uid, email.strip(), display_name.strip(), phone, now()],
    )
    return get_user(db, uid)


def get_or_create_user(db: Database, email: str, display_name: str | None = None) -> dict:
    u = get_user_by_email(db, email)
    if u:
        return u
    name = display_name or email.split("@")[0].title()
    return create_user(db, email, name)


def update_user(db: Database, user_id: str, **fields) -> dict | None:
    allowed = {"email", "display_name", "phone"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k} = ?")
            params.append(v)
    if sets:
        params.append(user_id)
        db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", params)
    return get_user(db, user_id)


def touch_login(db: Database, user_id: str) -> None:
    db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", [now(), user_id])


# --- syndicates ------------------------------------------------------------


def create_syndicate(db: Database, name: str, owner_id: str) -> dict:
    sid = new_id()
    base = slugify(name)
    slug, n = base, 1
    while db.value("SELECT 1 FROM syndicates WHERE slug = ?", [slug]):
        n += 1
        slug = f"{base}-{n}"
    ts = now()
    with db.write() as cur:
        cur.execute(
            "INSERT INTO syndicates (id, name, slug, owner_id, created_at) VALUES (?,?,?,?,?)",
            [sid, name.strip(), slug, owner_id, ts],
        )
        cur.execute(
            "INSERT INTO memberships (syndicate_id, user_id, role, joined_at) VALUES (?,?,?,?)",
            [sid, owner_id, "owner", ts],
        )
    return get_syndicate(db, sid)


def get_syndicate(db: Database, syndicate_id: str) -> dict | None:
    return db.row("SELECT * FROM syndicates WHERE id = ?", [syndicate_id])


def get_syndicate_by_slug(db: Database, slug: str) -> dict | None:
    return db.row("SELECT * FROM syndicates WHERE slug = ?", [slug])


def syndicates_for_user(db: Database, user_id: str) -> list[dict]:
    return db.rows(
        """SELECT s.*, m.role
           FROM syndicates s
           JOIN memberships m ON m.syndicate_id = s.id
           WHERE m.user_id = ?
           ORDER BY s.created_at""",
        [user_id],
    )


def members(db: Database, syndicate_id: str) -> list[dict]:
    return db.rows(
        """SELECT u.*, m.role, m.joined_at
           FROM memberships m
           JOIN users u ON u.id = m.user_id
           WHERE m.syndicate_id = ?
           ORDER BY m.joined_at, u.display_name""",
        [syndicate_id],
    )


def member_count(db: Database, syndicate_id: str) -> int:
    return int(db.value(
        "SELECT COUNT(*) FROM memberships WHERE syndicate_id = ?", [syndicate_id]
    ) or 0)


def is_member(db: Database, syndicate_id: str, user_id: str) -> bool:
    return bool(db.value(
        "SELECT 1 FROM memberships WHERE syndicate_id = ? AND user_id = ?",
        [syndicate_id, user_id],
    ))


def role_of(db: Database, syndicate_id: str, user_id: str) -> str | None:
    return db.value(
        "SELECT role FROM memberships WHERE syndicate_id = ? AND user_id = ?",
        [syndicate_id, user_id],
    )


def add_member(db: Database, syndicate_id: str, user_id: str, role: str = "member") -> None:
    if is_member(db, syndicate_id, user_id):
        return
    db.execute(
        "INSERT INTO memberships (syndicate_id, user_id, role, joined_at) VALUES (?,?,?,?)",
        [syndicate_id, user_id, role, now()],
    )


def remove_member(db: Database, syndicate_id: str, user_id: str) -> None:
    db.execute(
        "DELETE FROM memberships WHERE syndicate_id = ? AND user_id = ?",
        [syndicate_id, user_id],
    )


def update_syndicate(db: Database, syndicate_id: str, **fields) -> dict | None:
    allowed = {"name", "juice_odds", "lock_at_kickoff"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k} = ?")
            params.append(v)
    if sets:
        params.append(syndicate_id)
        db.execute(f"UPDATE syndicates SET {', '.join(sets)} WHERE id = ?", params)
    return get_syndicate(db, syndicate_id)


# --- invites ---------------------------------------------------------------


def create_invite(
    db: Database, syndicate_id: str, token_hash: str, email: str | None,
    invited_by: str | None, days: int = 14,
) -> str:
    iid = new_id()
    db.execute(
        """INSERT INTO invites (id, syndicate_id, email, token_hash, invited_by,
                                created_at, expires_at)
           VALUES (?,?,?,?,?,?,?)""",
        [iid, syndicate_id, email, token_hash, invited_by, now(),
         now() + timedelta(days=days)],
    )
    return iid


def get_invite(db: Database, token_hash: str) -> dict | None:
    return db.row("SELECT * FROM invites WHERE token_hash = ?", [token_hash])


def accept_invite(db: Database, token_hash: str, user_id: str) -> None:
    db.execute(
        "UPDATE invites SET accepted_at = ?, accepted_by = ? WHERE token_hash = ?",
        [now(), user_id, token_hash],
    )


def pending_invites(db: Database, syndicate_id: str) -> list[dict]:
    return db.rows(
        """SELECT * FROM invites
           WHERE syndicate_id = ? AND accepted_at IS NULL AND expires_at > ?
           ORDER BY created_at DESC""",
        [syndicate_id, now()],
    )


# --- login tokens ----------------------------------------------------------


def create_login_token(
    db: Database, token_hash: str, email: str, minutes: int, redirect_to: str | None
) -> None:
    db.execute(
        """INSERT INTO login_tokens (token_hash, email, created_at, expires_at, redirect_to)
           VALUES (?,?,?,?,?)""",
        [token_hash, email.strip().lower(), now(),
         now() + timedelta(minutes=minutes), redirect_to],
    )


def consume_login_token(db: Database, token_hash: str) -> dict | None:
    """Single use: returns the row only if unused and unexpired, and marks it."""
    with db.write() as cur:
        rows = cur.execute(
            """SELECT token_hash, email, expires_at, consumed_at, redirect_to
               FROM login_tokens WHERE token_hash = ?""",
            [token_hash],
        ).fetchall()
        if not rows:
            return None
        cols = ["token_hash", "email", "expires_at", "consumed_at", "redirect_to"]
        row = dict(zip(cols, rows[0]))
        if row["consumed_at"] is not None or row["expires_at"] < now():
            return None
        cur.execute(
            "UPDATE login_tokens SET consumed_at = ? WHERE token_hash = ?",
            [now(), token_hash],
        )
        return row


# --- sessions --------------------------------------------------------------


def create_session(db: Database, token_hash: str, user_id: str, days: int) -> None:
    ts = now()
    db.execute(
        """INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at)
           VALUES (?,?,?,?,?)""",
        [token_hash, user_id, ts, ts + timedelta(days=days), ts],
    )


def session_user(db: Database, token_hash: str) -> dict | None:
    row = db.row(
        """SELECT u.* FROM sessions s
           JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ? AND s.expires_at > ?""",
        [token_hash, now()],
    )
    return row


def touch_session(db: Database, token_hash: str) -> None:
    db.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
               [now(), token_hash])


def delete_session(db: Database, token_hash: str) -> None:
    db.execute("DELETE FROM sessions WHERE token_hash = ?", [token_hash])


def purge_expired(db: Database) -> None:
    ts = now()
    with db.write() as cur:
        cur.execute("DELETE FROM sessions WHERE expires_at < ?", [ts])
        cur.execute("DELETE FROM login_tokens WHERE expires_at < ?", [ts])
