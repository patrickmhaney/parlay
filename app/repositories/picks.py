"""Picks and their graded results."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.db import Database


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


PICK_SELECT = """
    SELECT p.*,
           u.display_name, u.email, u.phone,
           g.kickoff_at, g.status AS game_status, g.completed,
           g.home_score, g.away_score,
           g.home_team_id, g.away_team_id,
           h.display_name AS home_name, h.abbreviation AS home_abbr, h.short_name AS home_short,
           a.display_name AS away_name, a.abbreviation AS away_abbr, a.short_name AS away_short,
           st.display_name AS side_name, st.abbreviation AS side_abbr, st.short_name AS side_short,
           r.outcome, r.margin, r.graded_at, r.manual_override, r.note
    FROM picks p
    JOIN users u  ON u.id = p.user_id
    JOIN games g  ON g.id = p.game_id
    JOIN teams h  ON h.id = g.home_team_id
    JOIN teams a  ON a.id = g.away_team_id
    LEFT JOIN teams st ON st.id = p.side_team_id
    LEFT JOIN pick_results r ON r.pick_id = p.id
"""


def upsert_pick(
    db: Database, *, syndicate_id: str, user_id: str, game_id: str, season: int,
    week: int, bet_type: str, line: Decimal | str, side_team_id: str | None,
    source: str = "app",
) -> str:
    """One pick per player per week -- entering another replaces it in place
    (an UPDATE, not the delete-and-reinsert the old app did)."""
    existing = db.row(
        """SELECT id FROM picks
           WHERE syndicate_id = ? AND user_id = ? AND season = ? AND week = ?""",
        [syndicate_id, user_id, season, week],
    )
    ts = _now()
    if existing:
        pid = existing["id"]
        with db.write() as cur:
            cur.execute(
                """UPDATE picks SET game_id = ?, bet_type = ?, side_team_id = ?,
                       line = ?, updated_at = ?, source = ?
                   WHERE id = ?""",
                [game_id, bet_type, side_team_id, line, ts, source, pid],
            )
            # A changed pick is no longer graded.
            cur.execute("DELETE FROM pick_results WHERE pick_id = ?", [pid])
        return pid

    pid = uuid.uuid4().hex
    db.execute(
        """INSERT INTO picks (id, syndicate_id, user_id, game_id, season, week,
                              bet_type, side_team_id, line, created_at, updated_at, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        [pid, syndicate_id, user_id, game_id, season, week, bet_type,
         side_team_id, line, ts, ts, source],
    )
    return pid


def get_pick(db: Database, pick_id: str) -> dict | None:
    return db.row(PICK_SELECT + " WHERE p.id = ?", [pick_id])


def picks_for_week(db: Database, syndicate_id: str, season: int, week: int) -> list[dict]:
    return db.rows(
        PICK_SELECT
        + """ WHERE p.syndicate_id = ? AND p.season = ? AND p.week = ?
              ORDER BY p.created_at""",
        [syndicate_id, season, week],
    )


def pick_for_user_week(
    db: Database, syndicate_id: str, user_id: str, season: int, week: int
) -> dict | None:
    return db.row(
        PICK_SELECT
        + " WHERE p.syndicate_id = ? AND p.user_id = ? AND p.season = ? AND p.week = ?",
        [syndicate_id, user_id, season, week],
    )


def delete_pick(db: Database, pick_id: str) -> None:
    with db.write() as cur:
        cur.execute("DELETE FROM pick_results WHERE pick_id = ?", [pick_id])
        cur.execute("DELETE FROM picks WHERE id = ?", [pick_id])


def ungraded_picks(db: Database, syndicate_id: str | None = None) -> list[dict]:
    """Picks whose game is final but which have no result row yet."""
    sql = (
        PICK_SELECT
        + """ WHERE r.pick_id IS NULL AND g.completed
                AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL"""
    )
    params: list = []
    if syndicate_id:
        sql += " AND p.syndicate_id = ?"
        params.append(syndicate_id)
    return db.rows(sql + " ORDER BY p.season, p.week", params)


def save_result(
    db: Database, pick_id: str, outcome: str, margin: Decimal,
    manual_override: bool = False, note: str | None = None,
) -> None:
    db.execute(
        """INSERT INTO pick_results (pick_id, outcome, margin, graded_at, manual_override, note)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT (pick_id) DO UPDATE SET
               outcome = excluded.outcome,
               margin = excluded.margin,
               graded_at = excluded.graded_at,
               manual_override = excluded.manual_override,
               note = excluded.note""",
        [pick_id, outcome, margin, _now(), manual_override, note],
    )


# --- week locking ----------------------------------------------------------


def get_week_lock(db: Database, syndicate_id: str, season: int, week: int) -> dict | None:
    return db.row(
        "SELECT * FROM week_locks WHERE syndicate_id = ? AND season = ? AND week = ?",
        [syndicate_id, season, week],
    )


def lock_week(db: Database, syndicate_id: str, season: int, week: int) -> bool:
    """Returns True if this call is the one that locked it (so the caller and
    only the caller sends the notification)."""
    with db.write() as cur:
        rows = cur.execute(
            "SELECT locked_at FROM week_locks WHERE syndicate_id = ? AND season = ? AND week = ?",
            [syndicate_id, season, week],
        ).fetchall()
        if rows:
            return False
        cur.execute(
            "INSERT INTO week_locks (syndicate_id, season, week, locked_at) VALUES (?,?,?,?)",
            [syndicate_id, season, week, _now()],
        )
        return True


def mark_notified(db: Database, syndicate_id: str, season: int, week: int) -> None:
    db.execute(
        """UPDATE week_locks SET notified_at = ?
           WHERE syndicate_id = ? AND season = ? AND week = ?""",
        [_now(), syndicate_id, season, week],
    )


def weeks_with_picks(db: Database, syndicate_id: str, season: int) -> list[int]:
    return [r["week"] for r in db.rows(
        "SELECT DISTINCT week FROM picks WHERE syndicate_id = ? AND season = ? ORDER BY week",
        [syndicate_id, season],
    )]


def seasons_with_picks(db: Database, syndicate_id: str) -> list[int]:
    return [r["season"] for r in db.rows(
        "SELECT DISTINCT season FROM picks WHERE syndicate_id = ? ORDER BY season DESC",
        [syndicate_id],
    )]
