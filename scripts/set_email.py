#!/usr/bin/env python
"""Point a player at a real email address so they can sign in.

The migration seeds four of the five founders with placeholder .invalid
addresses, because only Pat's real address was known.

    python scripts/set_email.py Ben ben@example.com
    python scripts/set_email.py Ben ben@example.com --phone 5135551234
    python scripts/set_email.py --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_db                        # noqa: E402
from app.repositories import users as users_repo  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", help="display name, e.g. Ben")
    ap.add_argument("email", nargs="?")
    ap.add_argument("--phone", default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    db = get_db()
    db.migrate()

    if args.list or not args.name:
        print(f"{'name':<10} {'email':<36} phone")
        for u in db.rows("SELECT * FROM users ORDER BY display_name"):
            flag = "  <- placeholder" if u["email"].endswith(".invalid") else ""
            print(f"{u['display_name']:<10} {u['email']:<36} {u['phone'] or '-'}{flag}")
        return 0

    if not args.email:
        print("Give an email address, or use --list.")
        return 1

    user = db.row("SELECT * FROM users WHERE lower(display_name) = lower(?)", [args.name])
    if not user:
        print(f"No player called {args.name!r}. Use --list to see them.")
        return 1

    clash = users_repo.get_user_by_email(db, args.email)
    if clash and clash["id"] != user["id"]:
        print(f"{args.email} already belongs to {clash['display_name']}.")
        return 1

    users_repo.update_user(db, user["id"], email=args.email, phone=args.phone)
    updated = users_repo.get_user(db, user["id"])
    print(f"{updated['display_name']}: {updated['email']}"
          + (f" / {updated['phone']}" if updated["phone"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
