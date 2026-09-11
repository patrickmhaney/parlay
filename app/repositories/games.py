"""Teams and games: everything sourced from ESPN."""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import Database
from app.services.espn import Game, Team


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upsert_teams(db: Database, teams: list[Team]) -> int:
    if not teams:
        return 0
    sql = """
        INSERT INTO teams (id, abbreviation, display_name, short_name,
                           location, color, logo_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET
            abbreviation = excluded.abbreviation,
            display_name = excluded.display_name,
            short_name   = excluded.short_name,
            location     = excluded.location,
            color        = excluded.color,
            logo_url     = excluded.logo_url
    """
    with db.write() as cur:
        for t in teams:
            cur.execute(
                sql,
                [t.id, t.abbreviation, t.display_name, t.short_name,
                 t.location, t.color, t.logo_url],
            )
    return len(teams)


def upsert_games(db: Database, games: list[Game]) -> int:
    """Insert or refresh games. Scores and status always win from the feed;
    odds are only overwritten when the feed still carries them (ESPN drops the
    odds block once a game is final, and we want to keep what we captured)."""
    if not games:
        return 0
    sql = """
        INSERT INTO games (id, season, season_type, week, kickoff_at,
                           home_team_id, away_team_id, home_score, away_score,
                           status, completed, favorite_team_id, spread,
                           over_under, odds_provider, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET
            kickoff_at       = excluded.kickoff_at,
            home_score       = excluded.home_score,
            away_score       = excluded.away_score,
            status           = excluded.status,
            completed        = excluded.completed,
            favorite_team_id = COALESCE(excluded.favorite_team_id, games.favorite_team_id),
            spread           = COALESCE(excluded.spread, games.spread),
            over_under       = COALESCE(excluded.over_under, games.over_under),
            odds_provider    = COALESCE(excluded.odds_provider, games.odds_provider),
            synced_at        = excluded.synced_at
    """
    now = _now()
    with db.write() as cur:
        for g in games:
            cur.execute(
                sql,
                [g.id, g.season, g.season_type, g.week, g.kickoff_at,
                 g.home_team_id, g.away_team_id, g.home_score, g.away_score,
                 g.status, g.completed, g.favorite_team_id, g.spread,
                 g.over_under, g.odds_provider, now],
            )
    return len(games)


GAME_SELECT = """
    SELECT g.*,
           h.display_name AS home_name, h.abbreviation AS home_abbr,
           h.short_name AS home_short, h.color AS home_color,
           a.display_name AS away_name, a.abbreviation AS away_abbr,
           a.short_name AS away_short, a.color AS away_color
    FROM games g
    JOIN teams h ON h.id = g.home_team_id
    JOIN teams a ON a.id = g.away_team_id
"""


def games_for_week(db: Database, season: int, week: int) -> list[dict]:
    return db.rows(
        GAME_SELECT + " WHERE g.season = ? AND g.week = ? ORDER BY g.kickoff_at, g.id",
        [season, week],
    )


def get_game(db: Database, game_id: str) -> dict | None:
    return db.row(GAME_SELECT + " WHERE g.id = ?", [game_id])


def find_game_by_teams(
    db: Database, season: int, week: int, team_a_id: str, team_b_id: str
) -> dict | None:
    return db.row(
        GAME_SELECT
        + """ WHERE g.season = ? AND g.week = ?
              AND ((g.home_team_id = ? AND g.away_team_id = ?)
                OR (g.home_team_id = ? AND g.away_team_id = ?))""",
        [season, week, team_a_id, team_b_id, team_b_id, team_a_id],
    )


def teams_by_name(db: Database) -> dict[str, str]:
    return {r["display_name"]: r["id"] for r in db.rows("SELECT id, display_name FROM teams")}


def all_teams(db: Database) -> list[dict]:
    return db.rows("SELECT * FROM teams ORDER BY display_name")


def current_week(db: Database, season: int) -> int:
    """The week to show by default: the earliest week that isn't fully final,
    falling back to the last week of the season once everything is played."""
    row = db.row(
        """SELECT MIN(week) AS w FROM games
           WHERE season = ? AND season_type = 2 AND NOT completed""",
        [season],
    )
    if row and row["w"] is not None:
        return int(row["w"])
    row = db.row(
        "SELECT MAX(week) AS w FROM games WHERE season = ? AND season_type = 2",
        [season],
    )
    return int(row["w"]) if row and row["w"] is not None else 1


def seasons_available(db: Database) -> list[int]:
    return [r["season"] for r in db.rows(
        "SELECT DISTINCT season FROM games ORDER BY season DESC"
    )]
