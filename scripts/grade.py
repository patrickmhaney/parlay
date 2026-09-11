#!/usr/bin/env python
"""Grade every pick whose game is final. Safe to run repeatedly.

    python scripts/grade.py            # sync scores first, then grade
    python scripts/grade.py --no-sync
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings              # noqa: E402
from app.db import get_db                        # noqa: E402
from app.services import sync                    # noqa: E402
from app.services.espn import EspnClient         # noqa: E402
from app.services.picks_service import grade_pending  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sync", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    settings = get_settings()
    db = get_db()
    db.migrate()

    if not args.no_sync:
        client = EspnClient(settings.espn_cache_dir)
        n = sync.sync_live_weeks(db, client, settings.current_season)
        print(f"refreshed {n} games")

    result = grade_pending(db)
    print(f"graded {result['graded']} picks")
    for f in result["failed"]:
        print(f"  ! {f['pick_id']}: {f['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
