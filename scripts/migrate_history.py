#!/usr/bin/env python
"""Rebuild three seasons of pick history from the legacy SQLite archives.

The old app wiped its database every season and only ever kept weekly snapshots
in db_archive/. Those snapshots are the sole surviving record. Because the old
dedup logic deleted rows, no single snapshot holds a whole season -- so every
archive is read, in timestamp order, and the newest version of each
(season, week, player) pick wins.

    python scripts/migrate_history.py --dry-run
    python scripts/migrate_history.py
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings                    # noqa: E402
from app.db import get_db                              # noqa: E402
from app.repositories import games as games_repo       # noqa: E402
from app.repositories import picks as picks_repo       # noqa: E402
from app.repositories import users as users_repo       # noqa: E402
from app.services import grading                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

SYNDICATE_NAME = "Shed Parlay"

# The five founders. Pat's real address is known; the rest use the reserved
# .invalid TLD so a stray email can never reach a stranger. Fix them with:
#   python scripts/set_email.py Ben ben@example.com
SEED_PLAYERS = [
    ("Pat", "patrickmhaney@gmail.com"),
    ("Ben", "ben@parlaysyndicate.invalid"),
    ("Hank", "hank@parlaysyndicate.invalid"),
    ("Leland", "leland@parlaysyndicate.invalid"),
    ("BD", "bd@parlaysyndicate.invalid"),
]

BET_TYPE_MAP = {"spread": "SPREAD", "over": "OVER", "under": "UNDER"}


def season_of(ts: str) -> int:
    """Archive timestamp -> NFL season. Weeks 17-18 are played in January, so
    a January or February snapshot belongs to the *previous* season."""
    year, month = int(ts[:4]), int(ts[4:6])
    return year - 1 if month <= 2 else year


def legacy_sources() -> list[tuple[str, Path]]:
    """(timestamp, path) for every legacy database, oldest first."""
    out: list[tuple[str, Path]] = []
    for p in sorted((ROOT / "db_archive").glob("*_bets.db")):
        out.append((p.name[:14], p))
    live = ROOT / "bets.db"
    if live.exists():
        ts = datetime.fromtimestamp(live.stat().st_mtime).strftime("%Y%m%d%H%M%S")
        out.append((ts, live))
    out.sort(key=lambda t: t[0])
    return out


def collect_picks() -> dict[tuple[int, int, str], dict]:
    """Latest-wins merge across every archive, keyed by (season, week, player)."""
    latest: dict[tuple[int, int, str], dict] = {}
    for ts, path in legacy_sources():
        season = season_of(ts)
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT week, bet_type, player_name, winning_team, losing_team, value FROM bets"
            ).fetchall()
            conn.close()
        except sqlite3.Error as exc:
            print(f"  ! unreadable {path.name}: {exc}")
            continue
        for week, bet_type, player, win_team, lose_team, value in rows:
            if week is None or not player:
                continue
            key = (season, int(week), player.strip())
            prev = latest.get(key)
            if prev is None or ts >= prev["ts"]:
                latest[key] = {
                    "ts": ts, "source": path.name, "season": season,
                    "week": int(week), "player": player.strip(),
                    "bet_type": (bet_type or "").strip(),
                    "winning_team": (win_team or "").strip(),
                    "losing_team": (lose_team or "").strip(),
                    "value": (value or "").strip(),
                }
    return latest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    settings = get_settings()
    db = get_db()
    db.migrate()

    if not db.value("SELECT COUNT(*) FROM games"):
        print("No games in the database. Run scripts/sync_games.py first.")
        return 1

    print("=" * 68)
    print("LEGACY PICK MIGRATION")
    print("=" * 68)

    sources = legacy_sources()
    print(f"\nSources: {len(sources)} legacy databases")
    by_season_files = defaultdict(int)
    for ts, _ in sources:
        by_season_files[season_of(ts)] += 1
    for s in sorted(by_season_files):
        print(f"  season {s}: {by_season_files[s]} snapshots")

    picks = collect_picks()
    per_season = defaultdict(int)
    for (season, _, _) in picks:
        per_season[season] += 1
    print(f"\nDeduplicated picks: {len(picks)}")
    for s in sorted(per_season):
        print(f"  season {s}: {per_season[s]}")

    # --- users + syndicate ---
    name_to_user: dict[str, dict] = {}
    if args.dry_run:
        print("\n[dry run] would seed 5 users and the syndicate")
    else:
        owner = None
        for display, email in SEED_PLAYERS:
            u = users_repo.get_user_by_email(db, email)
            if not u:
                u = users_repo.create_user(db, email, display)
            name_to_user[display] = u
            if display == "Pat":
                owner = u
        syn = db.row("SELECT * FROM syndicates WHERE name = ?", [SYNDICATE_NAME])
        if not syn:
            syn = users_repo.create_syndicate(db, SYNDICATE_NAME, owner["id"])
        for display, _ in SEED_PLAYERS:
            users_repo.add_member(
                db, syn["id"], name_to_user[display]["id"],
                "owner" if display == "Pat" else "member",
            )
        print(f"\nSyndicate: {syn['name']} ({syn['slug']}) with "
              f"{users_repo.member_count(db, syn['id'])} members")

    # --- map picks onto real games ---
    team_ids = games_repo.teams_by_name(db)
    matched, unmatched, bad = [], [], []

    for key in sorted(picks):
        p = picks[key]
        bt = BET_TYPE_MAP.get(p["bet_type"].lower())
        if not bt:
            bad.append((p, f"unknown bet type {p['bet_type']!r}"))
            continue
        try:
            line = Decimal(p["value"].replace("+", ""))
        except (InvalidOperation, AttributeError):
            bad.append((p, f"unparseable line {p['value']!r}"))
            continue

        win_id = team_ids.get(p["winning_team"])
        lose_id = team_ids.get(p["losing_team"])
        if not win_id or not lose_id:
            missing = p["winning_team"] if not win_id else p["losing_team"]
            bad.append((p, f"unknown team {missing!r}"))
            continue

        game = games_repo.find_game_by_teams(db, p["season"], p["week"], win_id, lose_id)
        if not game:
            unmatched.append((p, win_id, lose_id))
            continue

        matched.append({
            **p, "bet_type": bt, "line": line,
            "game_id": game["id"],
            "side_team_id": win_id if bt == "SPREAD" else None,
        })

    print(f"\nGame matching:")
    print(f"  matched   {len(matched)}")
    print(f"  unmatched {len(unmatched)}")
    print(f"  malformed {len(bad)}")
    for p, w, l in unmatched[:20]:
        print(f"    ? {p['season']} wk{p['week']:>2} {p['player']:<7} "
              f"{p['winning_team']} vs {p['losing_team']}")
    for p, why in bad[:20]:
        print(f"    ! {p['season']} wk{p['week']:>2} {p['player']:<7} {why}")

    if args.dry_run:
        print("\n[dry run] nothing written")
        return 0

    # --- insert ---
    inserted = 0
    for m in matched:
        user = name_to_user.get(m["player"])
        if not user:
            bad.append((m, f"no seeded user for {m['player']!r}"))
            continue
        picks_repo.upsert_pick(
            db, syndicate_id=syn["id"], user_id=user["id"], game_id=m["game_id"],
            season=m["season"], week=m["week"], bet_type=m["bet_type"],
            line=m["line"], side_team_id=m["side_team_id"], source="migration",
        )
        inserted += 1
    print(f"\nInserted/updated picks: {inserted}")

    # --- grade ---
    graded, ungradeable = 0, []
    for p in picks_repo.ungraded_picks(db, syn["id"]):
        try:
            res = grading.grade(
                bet_type=p["bet_type"], line=p["line"],
                home_team_id=p["home_team_id"], away_team_id=p["away_team_id"],
                home_score=p["home_score"], away_score=p["away_score"],
                side_team_id=p["side_team_id"],
            )
        except grading.GradingError as exc:
            ungradeable.append((p, str(exc)))
            continue
        picks_repo.save_result(db, p["id"], res.outcome, res.margin)
        graded += 1
    print(f"Graded: {graded}   ungradeable: {len(ungradeable)}")
    for p, why in ungradeable[:10]:
        print(f"    ! {p['season']} wk{p['week']} {p['display_name']}: {why}")

    # --- reconciliation ---
    print("\n" + "=" * 68)
    print("RECONCILIATION")
    print("=" * 68)
    rows = db.rows(
        """SELECT p.season,
                  COUNT(*) AS picks,
                  COUNT(r.pick_id) AS graded,
                  SUM(CASE WHEN r.outcome = 'WIN'  THEN 1 ELSE 0 END) AS w,
                  SUM(CASE WHEN r.outcome = 'LOSS' THEN 1 ELSE 0 END) AS l,
                  SUM(CASE WHEN r.outcome = 'PUSH' THEN 1 ELSE 0 END) AS p
           FROM picks p LEFT JOIN pick_results r ON r.pick_id = p.id
           WHERE p.syndicate_id = ?
           GROUP BY p.season ORDER BY p.season""",
        [syn["id"]],
    )
    print(f"{'season':>7} {'picks':>6} {'graded':>7} {'W':>4} {'L':>4} {'P':>4}")
    for r in rows:
        print(f"{r['season']:>7} {r['picks']:>6} {r['graded']:>7} "
              f"{r['w'] or 0:>4} {r['l'] or 0:>4} {r['p'] or 0:>4}")

    expected = {2023: 90, 2024: 90, 2025: 85}
    print("\nExpected from the audit: 2023=90  2024=90  2025=85")
    ok = True
    for r in rows:
        exp = expected.get(r["season"])
        if exp and r["picks"] != exp:
            print(f"  MISMATCH season {r['season']}: got {r['picks']}, expected {exp}")
            ok = False
    print("  counts match the audit" if ok else "  *** investigate before deleting archives ***")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
