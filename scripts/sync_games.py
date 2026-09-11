#!/usr/bin/env python
"""Pull NFL schedule/odds/scores from ESPN into the database.

    python scripts/sync_games.py --seasons 2023 2024 2025 2026
    python scripts/sync_games.py --live          # only unfinished weeks
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings          # noqa: E402
from app.db import get_db                    # noqa: E402
from app.services.espn import EspnClient     # noqa: E402
from app.services import sync                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="*", default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="ignore the disk cache")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    db = get_db()
    db.migrate()
    client = EspnClient(settings.espn_cache_dir)

    n_teams = sync.sync_teams(db, client)
    print(f"teams: {n_teams}")

    if args.live:
        n = sync.sync_live_weeks(db, client, settings.current_season)
        print(f"live sync: {n} games refreshed")
        return 0

    seasons = args.seasons or [2023, 2024, 2025, 2026]
    grand = 0
    for s in seasons:
        n = sync.sync_season(db, client, s, refresh=args.refresh)
        grand += n
        print(f"season {s}: {n} games")
    print(f"total: {grand} games")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
