#!/usr/bin/env python
"""Capture every screen at phone and desktop widths, in light and dark.

Runs a private copy of the app on a spare port against a *copy* of the
database, with email in console/debug mode -- so it never sends real email
and never touches the live service.

    python scripts/screenshots.py                 # -> shots/
    python scripts/screenshots.py --out /tmp/x --only board
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8099
BASE = f"http://127.0.0.1:{PORT}"
SLUG = "shed-parlay"

VIEWPORTS = {"phone": (390, 844), "desktop": (1280, 900)}
THEMES = ("light", "dark")

# (name, path, needs_login)
PAGES = [
    ("signin", "/", False),
    ("board-current", f"/s/{SLUG}", True),
    ("board-graded", f"/s/{SLUG}?season=2025&week=16", True),
    ("stats", f"/s/{SLUG}/stats", True),
    ("stats-2025", f"/s/{SLUG}/stats?season=2025", True),
    ("settings", f"/s/{SLUG}/settings", True),
]


def start_server(db_copy: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "DATABASE_PATH": str(db_copy),
        "EMAIL_PROVIDER": "console",
        "DEBUG": "true",
        "SMS_ENABLED": "false",
        "SCHEDULER_ENABLED": "false",
        "BASE_URL": BASE,
        "RESEND_API_KEY": "",
    }
    proc = subprocess.Popen(
        [str(ROOT / ".venv/bin/uvicorn"), "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/health", timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("screenshot server did not start")


def sign_in(page) -> None:
    page.goto(BASE + "/login")
    page.fill("input[name=email]", "patrickmhaney@gmail.com")
    page.click("button[type=submit], button:not([type])")
    html = page.content()
    m = re.search(r'(/auth/verify\?token=[A-Za-z0-9_-]+)', html)
    if not m:
        raise SystemExit("no dev sign-in link on the page (is DEBUG honoured?)")
    page.goto(BASE + m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "shots"))
    ap.add_argument("--only", default="", help="substring filter on page name")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="parlay-shots-"))
    db_copy = tmp / "shots.duckdb"
    shutil.copy(ROOT / "data" / "parlay.duckdb", db_copy)
    wal = ROOT / "data" / "parlay.duckdb.wal"
    if wal.exists():
        shutil.copy(wal, tmp / "shots.duckdb.wal")

    proc = start_server(db_copy)
    written = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # Sign in once and reuse the session everywhere -- signing in per
            # context would trip the app's 3-links-per-15-minutes limit.
            login_ctx = browser.new_context()
            sign_in(login_ctx.new_page())
            session = login_ctx.storage_state()
            login_ctx.close()

            for vname, (w, h) in VIEWPORTS.items():
                for theme in THEMES:
                    common = dict(
                        viewport={"width": w, "height": h},
                        color_scheme=theme,
                        device_scale_factor=2 if vname == "phone" else 1,
                    )
                    anon = browser.new_context(**common).new_page()
                    ctx = browser.new_context(storage_state=session, **common)
                    authed = ctx.new_page()
                    for name, path, needs_login in PAGES:
                        if args.only and args.only not in name:
                            continue
                        page = authed if needs_login else anon
                        page.goto(BASE + path, wait_until="networkidle")
                        f = out / f"{name}-{vname}-{theme}.png"
                        page.screenshot(path=str(f), full_page=True)
                        written.append(f)
                    ctx.close()
                    anon.context.close()
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)

    for f in written:
        print(f.relative_to(out.parent) if out.parent in f.parents else f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
