"""Analytics. Every query is scoped to one syndicate and, optionally, one
season. Units are computed from the syndicate's juice (default -110).

DuckDB does the aggregation; the templates just draw it.
"""
from __future__ import annotations

from app.db import Database

# Units on a 1-unit stake. Kept as SQL so it stays consistent everywhere.
UNITS = """
    CASE r.outcome
        WHEN 'WIN'  THEN CAST(100.0 AS DOUBLE) / ABS(?)
        WHEN 'LOSS' THEN -1.0
        ELSE 0.0
    END
"""

GRADED_JOIN = """
    FROM picks p
    JOIN users u ON u.id = p.user_id
    JOIN pick_results r ON r.pick_id = p.id
    JOIN games g ON g.id = p.game_id
"""


def _season_clause(season: int | None) -> tuple[str, list]:
    return (" AND p.season = ?", [season]) if season else ("", [])


def leaderboard(db: Database, syndicate_id: str, season: int | None = None,
                juice: int = -110) -> list[dict]:
    sc, sp = _season_clause(season)
    return db.rows(
        f"""
        SELECT u.id AS user_id, u.display_name,
               COUNT(*) AS graded,
               SUM(CASE WHEN r.outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN r.outcome='PUSH' THEN 1 ELSE 0 END) AS pushes,
               ROUND(SUM({UNITS}), 2) AS units,
               ROUND(100.0 * SUM(CASE WHEN r.outcome='WIN' THEN 1 ELSE 0 END)
                     / NULLIF(SUM(CASE WHEN r.outcome IN ('WIN','LOSS') THEN 1 ELSE 0 END), 0), 1)
                     AS win_pct,
               ROUND(AVG(CAST(r.margin AS DOUBLE)), 2) AS avg_margin
        {GRADED_JOIN}
        WHERE p.syndicate_id = ?{sc}
        GROUP BY 1, 2
        ORDER BY units DESC, wins DESC
        """,
        [juice, syndicate_id, *sp],
    )


def syndicate_totals(db: Database, syndicate_id: str, season: int | None = None,
                     juice: int = -110) -> dict:
    sc, sp = _season_clause(season)
    row = db.row(
        f"""
        SELECT COUNT(*) AS graded,
               SUM(CASE WHEN r.outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN r.outcome='PUSH' THEN 1 ELSE 0 END) AS pushes,
               ROUND(SUM({UNITS}), 2) AS units,
               COUNT(DISTINCT p.season) AS seasons,
               COUNT(DISTINCT p.week) AS weeks
        {GRADED_JOIN}
        WHERE p.syndicate_id = ?{sc}
        """,
        [juice, syndicate_id, *sp],
    )
    return row or {}


def cumulative_units(db: Database, syndicate_id: str, season: int,
                     juice: int = -110) -> dict[str, list[dict]]:
    """Running unit total per player, week by week -- the most-argued-about
    graph in the app."""
    rows = db.rows(
        f"""
        SELECT u.display_name, p.week,
               SUM({UNITS}) AS units
        {GRADED_JOIN}
        WHERE p.syndicate_id = ? AND p.season = ?
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        [juice, syndicate_id, season],
    )
    series: dict[str, list[dict]] = {}
    running: dict[str, float] = {}
    for r in rows:
        name = r["display_name"]
        running[name] = running.get(name, 0.0) + float(r["units"] or 0)
        series.setdefault(name, []).append(
            {"week": r["week"], "units": round(running[name], 3)}
        )
    return series


def weekly_grid(db: Database, syndicate_id: str, season: int) -> list[dict]:
    """One row per week with each player's outcome -- the season at a glance."""
    return db.rows(
        """
        SELECT p.week, u.display_name, r.outcome, r.margin,
               p.bet_type, p.line,
               COALESCE(st.abbreviation, '') AS side_abbr,
               ha.abbreviation AS home_abbr, aa.abbreviation AS away_abbr
        FROM picks p
        JOIN users u ON u.id = p.user_id
        JOIN games g ON g.id = p.game_id
        JOIN teams ha ON ha.id = g.home_team_id
        JOIN teams aa ON aa.id = g.away_team_id
        LEFT JOIN teams st ON st.id = p.side_team_id
        LEFT JOIN pick_results r ON r.pick_id = p.id
        WHERE p.syndicate_id = ? AND p.season = ?
        ORDER BY p.week, u.display_name
        """,
        [syndicate_id, season],
    )


def streaks(db: Database, syndicate_id: str) -> list[dict]:
    """Current and longest win/loss streaks. Pushes don't break a streak."""
    rows = db.rows(
        """
        SELECT u.display_name, p.season, p.week, r.outcome
        FROM picks p
        JOIN users u ON u.id = p.user_id
        JOIN pick_results r ON r.pick_id = p.id
        WHERE p.syndicate_id = ?
        ORDER BY u.display_name, p.season, p.week
        """,
        [syndicate_id],
    )
    by_player: dict[str, list[str]] = {}
    for r in rows:
        if r["outcome"] != "PUSH":
            by_player.setdefault(r["display_name"], []).append(r["outcome"])

    out = []
    for name, seq in by_player.items():
        best_w = best_l = cur = 0
        cur_kind = None
        for o in seq:
            if o == cur_kind:
                cur += 1
            else:
                cur_kind, cur = o, 1
            if cur_kind == "WIN":
                best_w = max(best_w, cur)
            else:
                best_l = max(best_l, cur)
        out.append({
            "display_name": name,
            "current": cur,
            "current_kind": cur_kind,
            "longest_win": best_w,
            "longest_loss": best_l,
        })
    return sorted(out, key=lambda r: (-r["longest_win"], r["display_name"]))


def by_bet_type(db: Database, syndicate_id: str, season: int | None = None,
                juice: int = -110) -> list[dict]:
    sc, sp = _season_clause(season)
    return db.rows(
        f"""
        SELECT u.display_name, p.bet_type,
               COUNT(*) AS n,
               SUM(CASE WHEN r.outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN r.outcome='PUSH' THEN 1 ELSE 0 END) AS pushes,
               ROUND(SUM({UNITS}), 2) AS units
        {GRADED_JOIN}
        WHERE p.syndicate_id = ?{sc}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        [juice, syndicate_id, *sp],
    )


def favorite_vs_dog(db: Database, syndicate_id: str, season: int | None = None,
                    juice: int = -110) -> list[dict]:
    """Spread picks only: taking points versus laying them."""
    sc, sp = _season_clause(season)
    return db.rows(
        f"""
        SELECT u.display_name,
               CASE WHEN p.line < 0 THEN 'favorite'
                    WHEN p.line > 0 THEN 'underdog'
                    ELSE 'pick-em' END AS side,
               COUNT(*) AS n,
               SUM(CASE WHEN r.outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
               ROUND(SUM({UNITS}), 2) AS units
        {GRADED_JOIN}
        WHERE p.syndicate_id = ? AND p.bet_type = 'SPREAD'{sc}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        [juice, syndicate_id, *sp],
    )


def home_vs_away(db: Database, syndicate_id: str, season: int | None = None,
                 juice: int = -110) -> list[dict]:
    sc, sp = _season_clause(season)
    return db.rows(
        f"""
        SELECT u.display_name,
               CASE WHEN p.side_team_id = g.home_team_id THEN 'home' ELSE 'away' END AS side,
               COUNT(*) AS n,
               SUM(CASE WHEN r.outcome='WIN' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
               ROUND(SUM({UNITS}), 2) AS units
        {GRADED_JOIN}
        WHERE p.syndicate_id = ? AND p.bet_type = 'SPREAD'
              AND p.side_team_id IS NOT NULL{sc}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        [juice, syndicate_id, *sp],
    )


def team_loyalty(db: Database, syndicate_id: str, limit: int = 60,
                 juice: int = -110) -> list[dict]:
    """Which teams each player rides, and how it goes. Spread picks only --
    a total isn't a bet on a team."""
    return db.rows(
        f"""
        SELECT u.display_name, t.display_name AS team, t.abbreviation,
               COUNT(*) AS n,
               SUM(CASE WHEN r.outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
               ROUND(SUM({UNITS}), 2) AS units
        {GRADED_JOIN}
        JOIN teams t ON t.id = p.side_team_id
        WHERE p.syndicate_id = ? AND p.bet_type = 'SPREAD'
        GROUP BY 1, 2, 3
        HAVING COUNT(*) >= 2
        ORDER BY n DESC, units DESC
        LIMIT ?
        """,
        [juice, syndicate_id, limit],
    )


def weekly_winners(db: Database, syndicate_id: str, season: int | None = None) -> list[dict]:
    """How often each player won a week that not everyone won -- the real
    bragging metric, since everyone picks a different game."""
    sc, sp = _season_clause(season)
    rows = db.rows(
        f"""
        SELECT p.season, p.week, u.display_name, r.outcome
        FROM picks p
        JOIN users u ON u.id = p.user_id
        JOIN pick_results r ON r.pick_id = p.id
        WHERE p.syndicate_id = ?{sc}
        """,
        [syndicate_id, *sp],
    )
    weeks: dict[tuple, list] = {}
    for r in rows:
        weeks.setdefault((r["season"], r["week"]), []).append(r)

    tally: dict[str, dict] = {}
    for (_season, _week), entries in weeks.items():
        winners = [e["display_name"] for e in entries if e["outcome"] == "WIN"]
        # Only interesting when it wasn't a clean sweep.
        if not winners or len(winners) == len(entries):
            continue
        for name in winners:
            t = tally.setdefault(name, {"display_name": name, "solo": 0, "shared": 0})
            if len(winners) == 1:
                t["solo"] += 1
            else:
                t["shared"] += 1
    out = list(tally.values())
    for t in out:
        t["total"] = t["solo"] + t["shared"]
    return sorted(out, key=lambda r: (-r["solo"], -r["total"]))


def bad_beats(db: Database, syndicate_id: str, limit: int = 12) -> list[dict]:
    """Losses by a point or less. Purely so they can be brought up later."""
    return db.rows(
        """
        SELECT u.display_name, p.season, p.week, p.bet_type, p.line, r.margin,
               COALESCE(st.abbreviation, '') AS side_abbr,
               ha.abbreviation AS home_abbr, aa.abbreviation AS away_abbr,
               g.home_score, g.away_score
        FROM picks p
        JOIN users u ON u.id = p.user_id
        JOIN pick_results r ON r.pick_id = p.id
        JOIN games g ON g.id = p.game_id
        JOIN teams ha ON ha.id = g.home_team_id
        JOIN teams aa ON aa.id = g.away_team_id
        LEFT JOIN teams st ON st.id = p.side_team_id
        WHERE p.syndicate_id = ? AND r.outcome = 'LOSS' AND r.margin >= -1.0
        ORDER BY r.margin DESC, p.season DESC, p.week DESC
        LIMIT ?
        """,
        [syndicate_id, limit],
    )


def season_summary(db: Database, syndicate_id: str, juice: int = -110) -> list[dict]:
    return db.rows(
        f"""
        SELECT p.season, u.display_name,
               SUM(CASE WHEN r.outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN r.outcome='PUSH' THEN 1 ELSE 0 END) AS pushes,
               ROUND(SUM({UNITS}), 2) AS units
        {GRADED_JOIN}
        WHERE p.syndicate_id = ?
        GROUP BY 1, 2
        ORDER BY 1 DESC, units DESC
        """,
        [juice, syndicate_id],
    )


def never_picked_teams(db: Database, syndicate_id: str) -> list[str]:
    return [r["display_name"] for r in db.rows(
        """
        SELECT t.display_name FROM teams t
        WHERE t.id NOT IN (
            SELECT g.home_team_id FROM picks p JOIN games g ON g.id = p.game_id
            WHERE p.syndicate_id = ?
            UNION
            SELECT g.away_team_id FROM picks p JOIN games g ON g.id = p.game_id
            WHERE p.syndicate_id = ?
        )
        ORDER BY t.display_name
        """,
        [syndicate_id, syndicate_id],
    )]
