"""Stats. Every query is scoped to one syndicate and, optionally, one season.

Two levels matter in this game:
  * the parlay -- the week's shared bet, which hits only if no leg loses;
  * the legs -- each member's individual pick, for bragging rights.
"""
from __future__ import annotations

from collections import defaultdict

from app.db import Database
from app.services.parlay import HIT, Leg, evaluate

GRADED_JOIN = """
    FROM picks p
    JOIN users u ON u.id = p.user_id
    JOIN pick_results r ON r.pick_id = p.id
    JOIN games g ON g.id = p.game_id
"""

W = "SUM(CASE WHEN r.outcome='WIN'  THEN 1 ELSE 0 END)"
L = "SUM(CASE WHEN r.outcome='LOSS' THEN 1 ELSE 0 END)"
P = "SUM(CASE WHEN r.outcome='PUSH' THEN 1 ELSE 0 END)"
PCT = f"ROUND(100.0 * {W} / NULLIF({W} + {L}, 0), 1)"


def _season(season: int | None) -> tuple[str, list]:
    return (" AND p.season = ?", [season]) if season else ("", [])


# --- parlays ---------------------------------------------------------------


def parlay_weeks(db: Database, syndicate_id: str, season: int | None = None) -> list[dict]:
    """Every week that has picks, newest first, with its parlay result."""
    sc, sp = _season(season)
    rows = db.rows(
        f"""SELECT p.season, p.week, u.display_name, r.outcome
            FROM picks p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN pick_results r ON r.pick_id = p.id
            WHERE p.syndicate_id = ?{sc}
            ORDER BY p.season DESC, p.week DESC, u.display_name""",
        [syndicate_id, *sp],
    )
    weeks: dict[tuple, list[Leg]] = defaultdict(list)
    for r in rows:
        weeks[(r["season"], r["week"])].append(Leg(r["display_name"], r["outcome"]))
    return [{"season": s, "week": w, "result": evaluate(legs)} for (s, w), legs in weeks.items()]


def week_parlay(db: Database, syndicate_id: str, season: int, week: int):
    rows = db.rows(
        """SELECT u.display_name, r.outcome
           FROM picks p JOIN users u ON u.id = p.user_id
           LEFT JOIN pick_results r ON r.pick_id = p.id
           WHERE p.syndicate_id = ? AND p.season = ? AND p.week = ?""",
        [syndicate_id, season, week],
    )
    return evaluate([Leg(r["display_name"], r["outcome"]) for r in rows])


def parlay_summary(weeks: list[dict]) -> dict:
    settled = [w for w in weeks if w["result"].status in (HIT, "MISSED", "VOID")]
    hits = [w for w in weeks if w["result"].status == HIT]
    geese = [w for w in weeks if w["result"].goose]
    return {"settled": len(settled), "hits": hits, "geese": len(geese)}


def goose_counts(db: Database, syndicate_id: str, weeks: list[dict]) -> list[dict]:
    """Every member, with how often they were the goose and when it last
    happened. Members with zero stay on the list -- that's the brag."""
    tally: dict[str, dict] = {}
    for w in weeks:                               # newest first
        g = w["result"].goose
        if g:
            t = tally.setdefault(g, {"count": 0, "last": None})
            t["count"] += 1
            t["last"] = t["last"] or (w["season"], w["week"])
    names = [r["display_name"] for r in db.rows(
        """SELECT u.display_name FROM memberships m JOIN users u ON u.id = m.user_id
           WHERE m.syndicate_id = ?""", [syndicate_id])]
    out = [{"display_name": n, **tally.get(n, {"count": 0, "last": None})} for n in names]
    return sorted(out, key=lambda r: (-r["count"], r["display_name"]))


# --- legs ------------------------------------------------------------------


def leaderboard(db: Database, syndicate_id: str, season: int | None = None) -> list[dict]:
    sc, sp = _season(season)
    return db.rows(
        f"""SELECT u.id AS user_id, u.display_name, COUNT(*) AS graded,
                   {W} AS wins, {L} AS losses, {P} AS pushes, {PCT} AS win_pct
            {GRADED_JOIN}
            WHERE p.syndicate_id = ?{sc}
            GROUP BY 1, 2
            ORDER BY win_pct DESC NULLS LAST, wins DESC""",
        [syndicate_id, *sp],
    )


def syndicate_totals(db: Database, syndicate_id: str, season: int | None = None) -> dict:
    sc, sp = _season(season)
    return db.row(
        f"""SELECT COUNT(*) AS graded, {W} AS wins, {L} AS losses, {P} AS pushes,
                   COUNT(DISTINCT p.season) AS seasons
            {GRADED_JOIN}
            WHERE p.syndicate_id = ?{sc}""",
        [syndicate_id, *sp],
    ) or {}


def running_record(db: Database, syndicate_id: str, season: int) -> dict[str, list[dict]]:
    """Wins minus losses, week by week, per player."""
    rows = db.rows(
        f"""SELECT u.display_name, p.week, {W} - {L} AS net
            {GRADED_JOIN}
            WHERE p.syndicate_id = ? AND p.season = ?
            GROUP BY 1, 2 ORDER BY 1, 2""",
        [syndicate_id, season],
    )
    series: dict[str, list[dict]] = {}
    running: dict[str, int] = {}
    for r in rows:
        n = r["display_name"]
        running[n] = running.get(n, 0) + int(r["net"] or 0)
        series.setdefault(n, []).append({"week": r["week"], "value": running[n]})
    return series


def streaks(db: Database, syndicate_id: str) -> list[dict]:
    """Current and longest win/loss streaks. Pushes don't break a streak."""
    rows = db.rows(
        """SELECT u.display_name, r.outcome
           FROM picks p JOIN users u ON u.id = p.user_id
           JOIN pick_results r ON r.pick_id = p.id
           WHERE p.syndicate_id = ?
           ORDER BY u.display_name, p.season, p.week""",
        [syndicate_id],
    )
    seqs: dict[str, list[str]] = {}
    for r in rows:
        if r["outcome"] != "PUSH":
            seqs.setdefault(r["display_name"], []).append(r["outcome"])
    out = []
    for name, seq in seqs.items():
        best_w = best_l = cur = 0
        kind = None
        for o in seq:
            cur, kind = (cur + 1, kind) if o == kind else (1, o)
            if kind == "WIN":
                best_w = max(best_w, cur)
            else:
                best_l = max(best_l, cur)
        out.append({"display_name": name, "current": cur, "current_kind": kind,
                    "longest_win": best_w, "longest_loss": best_l})
    return out


def by_bet_type(db: Database, syndicate_id: str, season: int | None = None) -> list[dict]:
    sc, sp = _season(season)
    return db.rows(
        f"""SELECT u.display_name, p.bet_type, {W} AS wins, {L} AS losses, {P} AS pushes
            {GRADED_JOIN}
            WHERE p.syndicate_id = ?{sc}
            GROUP BY 1, 2""",
        [syndicate_id, *sp],
    )


def favorite_vs_dog(db: Database, syndicate_id: str, season: int | None = None) -> list[dict]:
    sc, sp = _season(season)
    return db.rows(
        f"""SELECT u.display_name,
                   CASE WHEN p.line < 0 THEN 'favorite' WHEN p.line > 0 THEN 'underdog'
                        ELSE 'pick-em' END AS side,
                   {W} AS wins, {L} AS losses, {P} AS pushes
            {GRADED_JOIN}
            WHERE p.syndicate_id = ? AND p.bet_type = 'SPREAD'{sc}
            GROUP BY 1, 2""",
        [syndicate_id, *sp],
    )


def team_loyalty(db: Database, syndicate_id: str, limit: int = 10) -> list[dict]:
    return db.rows(
        f"""SELECT u.display_name, t.display_name AS team, COUNT(*) AS n,
                   {W} AS wins, {L} AS losses
            {GRADED_JOIN}
            JOIN teams t ON t.id = p.side_team_id
            WHERE p.syndicate_id = ? AND p.bet_type = 'SPREAD'
            GROUP BY 1, 2
            HAVING COUNT(*) >= 2
            ORDER BY n DESC, wins DESC
            LIMIT ?""",
        [syndicate_id, limit],
    )


def bad_beats(db: Database, syndicate_id: str, limit: int = 8) -> list[dict]:
    """Losses by a point or less."""
    return db.rows(
        """SELECT u.display_name, p.season, p.week, p.bet_type, p.line, r.margin,
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
           LIMIT ?""",
        [syndicate_id, limit],
    )
