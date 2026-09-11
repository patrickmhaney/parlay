"""Pulls schedule, odds and scores from ESPN into the database."""
from __future__ import annotations

import logging

from app.db import Database
from app.repositories import games as games_repo
from app.services.espn import EspnClient, REGULAR_SEASON, weeks_in_season

log = logging.getLogger(__name__)


def sync_teams(db: Database, client: EspnClient) -> int:
    return games_repo.upsert_teams(db, client.teams())


def sync_week(
    db: Database, client: EspnClient, season: int, week: int, *, refresh: bool = False
) -> int:
    games = client.games(season, week, REGULAR_SEASON, refresh=refresh)
    if games:
        # Team rows must exist before games reference them.
        seen: dict[str, object] = {}
        for g in games:
            for t in g.teams:
                seen[t.id] = t
        games_repo.upsert_teams(db, list(seen.values()))
    return games_repo.upsert_games(db, games)


def sync_season(
    db: Database, client: EspnClient, season: int, *, refresh: bool = False
) -> int:
    total = 0
    for week in range(1, weeks_in_season(season) + 1):
        try:
            n = sync_week(db, client, season, week, refresh=refresh)
            total += n
            log.info("synced %s week %s: %s games", season, week, n)
        except Exception as exc:
            log.error("sync failed for %s week %s: %s", season, week, exc)
    return total


def sync_live_weeks(db: Database, client: EspnClient, season: int) -> int:
    """Refresh only weeks that still have unfinished games -- what the
    scheduled job runs. Cheap: a handful of requests."""
    rows = db.rows(
        """SELECT DISTINCT week FROM games
           WHERE season = ? AND season_type = 2 AND NOT completed
           ORDER BY week""",
        [season],
    )
    weeks = [r["week"] for r in rows] or [1]
    total = 0
    for w in weeks:
        try:
            total += sync_week(db, client, season, w, refresh=True)
        except Exception as exc:
            log.error("live sync failed for %s week %s: %s", season, w, exc)
    return total
