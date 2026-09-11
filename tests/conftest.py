"""Test fixtures.

The app's lifespan closes the database on shutdown, and TestClient runs a full
lifespan per test, so any handle must be re-fetched per test rather than held
at session scope. `seeded` therefore returns plain data, never a connection.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="parlay-test-"))
os.environ["DATABASE_PATH"] = str(TMP / "test.duckdb")
os.environ["ESPN_CACHE_DIR"] = str(TMP / "cache")
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["SMS_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "test-key"
os.environ["BASE_URL"] = "http://testserver"
os.environ["CURRENT_SEASON"] = "2026"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import get_db  # noqa: E402
from app.repositories import users as users_repo  # noqa: E402

SEASON, WEEK = 2026, 1
HOME, AWAY = "100", "200"
WEEKS = range(1, 7)


def game_id(week: int = WEEK) -> str:
    return f"test-game-{week}"


GAME_ID = game_id(WEEK)


@pytest.fixture(scope="session", autouse=True)
def seeded():
    """Seed the file once. Returns plain dicts -- no live connection."""
    d = get_db()
    d.migrate()
    with d.write() as cur:
        for tid, abbr, name, short in [
            (HOME, "HOM", "Home Herons", "Herons"),
            (AWAY, "AWY", "Away Antelopes", "Antelopes"),
        ]:
            cur.execute(
                """INSERT INTO teams (id, abbreviation, display_name, short_name)
                   VALUES (?,?,?,?) ON CONFLICT (id) DO NOTHING""",
                [tid, abbr, name, short],
            )
        # One game per week, so a test can use its own week without colliding
        # with the one-pick-per-player-per-week rule.
        for w in WEEKS:
            cur.execute(
                """INSERT INTO games (id, season, season_type, week, kickoff_at,
                       home_team_id, away_team_id, status, completed,
                       favorite_team_id, spread, over_under, odds_provider, synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT (id) DO NOTHING""",
                [game_id(w), SEASON, 2, w, datetime.utcnow() + timedelta(days=2 + w),
                 HOME, AWAY, "STATUS_SCHEDULED", False, HOME, -3.5, 44.5,
                 "DraftKings", datetime.utcnow()],
            )

    owner = users_repo.get_or_create_user(d, "owner@example.com", "Owner")
    friend = users_repo.get_or_create_user(d, "friend@example.com", "Friend")
    syn = d.row("SELECT * FROM syndicates WHERE name = ?", ["Test Syndicate"])
    if not syn:
        syn = users_repo.create_syndicate(d, "Test Syndicate", owner["id"])
    users_repo.add_member(d, syn["id"], friend["id"])
    return {"owner": dict(owner), "friend": dict(friend), "syndicate": dict(syn)}


@pytest.fixture()
def db():
    """A live handle for this test. Re-fetched because the previous test's
    TestClient shutdown closed and cleared the singleton."""
    return get_db()


@pytest.fixture()
def people(seeded):
    return seeded


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def login(client, db, email: str) -> None:
    """Drive the real magic-link flow rather than forging a cookie."""
    from app.services import auth
    link = auth.issue_login_link(db, email, None)
    token = link.split("token=")[1]
    r = client.get("/auth/verify", params={"token": token}, follow_redirects=False)
    assert r.status_code == 303, r.text
