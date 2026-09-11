# Parlay Syndicate

Weekly NFL parlay. Each member picks one leg — a spread or a total — and
the group bets them together as a single parlay: it hits only if no leg
loses. The board locks when everyone's in, the app grades every leg from the
final scores, and whoever's loss sank an otherwise-winning parlay is the goose.

Rebuilt from the 2023 FastAPI original. The plan behind the rebuild is in
[REBUILD_PLAN.md](REBUILD_PLAN.md).

```
FastAPI + Jinja + HTMX  ·  DuckDB (single file)  ·  Tailwind (no node)
Scores & lines: ESPN     ·  Auth: email magic link, 120-day sessions
```

---

## Quick start

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as SECRET_KEY

.venv/bin/python scripts/sync_games.py --seasons 2023 2024 2025 2026
.venv/bin/python scripts/migrate_history.py      # imports the legacy archives
./run.sh                                          # http://localhost:8080
```

With `EMAIL_PROVIDER=console` (the default) sign-in links are printed to the
log and written to `data/outbox/`, so you can sign in without configuring email.

---

## The one operational rule

**Run exactly one worker.** DuckDB permits a single writer and takes an
exclusive lock on the database file. A second uvicorn worker — or a second
process, including a `scripts/` command while the server is running — cannot
open it for writing and will fail with:

```
IO Error: Could not set lock on file ... Conflicting lock is held
```

Stop the server before running a script that writes. All writes inside the app
funnel through one process-wide lock in `app/db.py`.

---

## Layout

```
app/
  config.py          settings, entirely from the environment
  db.py              DuckDB layer: write lock, thread-local cursors, migrations
  deps.py            templates, auth guards, syndicate scoping
  migrations/        numbered .sql, applied at startup
  repositories/      all SQL lives here (games, users, picks, stats)
  services/
    espn.py          the only module that knows ESPN's JSON
    grading.py       pure win/loss/push rules — no DB, no network
    picks_service.py validation, locking, notification, grading sweep
    auth.py          magic links and sessions
    notify.py        email + SMS over HTTP (never a shell)
    charts.py        SVG geometry for the dashboard
    scheduler.py     APScheduler jobs
  routers/           HTTP only; no business logic
  templates/         Jinja + HTMX
scripts/             sync_games, migrate_history, grade, set_email
legacy/              the 2023 app, retired and kept for reference only
```

---

## How a week runs

| When | What happens |
|---|---|
| Tue | Schedule and opening lines sync from ESPN |
| Tue–Sun | Members pick: choose a game, the line pre-fills, adjust if your book differs |
| On the last pick | Board locks, "the picks are in" text goes out |
| Sun–Mon | Everyone places their own bet at their own book |
| Tue 06:00 ET | Scores sync, every pick is graded, results text goes out |

The lock threshold is the syndicate's **member count**, not a hardcoded 5.

### Grading rules

- **Spread** — your team's score + your line vs. theirs. `> 0` win, `< 0` loss, `0` push.
- **Over** — combined total above your number wins, below loses, equal pushes.
- **Under** — the reverse.

Every result stores its margin, so a wrong call shows on the board rather than
hiding. `tests/test_grading.py` pins all of it, exact pushes included.

---

## Common tasks

```bash
make test          # 42 tests
make sync          # refresh the current season
make grade         # grade anything final
make css           # rebuild Tailwind (needs tools/tailwindcss — see below)
make backup        # snapshot the database
make shots         # screenshot every screen, phone+desktop, light+dark

.venv/bin/python scripts/set_email.py --list
.venv/bin/python scripts/set_email.py Ben ben@example.com --phone 5135551234
```

### Rebuilding CSS

The built `app/static/css/app.css` is committed, so deploys need neither node
nor the Tailwind binary. To change styles, fetch the standalone CLI once:

```bash
curl -sSL -o tools/tailwindcss \
  https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64
chmod +x tools/tailwindcss
make css
```

---

## Deploying

### How it's actually deployed (parlay-vm)

The VM already runs nginx on :80 for other sites (haneytube.com and friends),
so parlay follows the same pattern rather than bringing its own proxy:

```
browser --https--> Cloudflare --:8080 (origin rule) / :80 / :443--> nginx --> 127.0.0.1:8081 (uvicorn, systemd)
```

| File in repo | Installed as |
|---|---|
| `deploy/systemd/parlay.service` | `/etc/systemd/system/parlay.service` |
| `deploy/nginx/parlaysyndicate` | `/etc/nginx/sites-available/parlaysyndicate` (+ symlink in `sites-enabled`) |
| — | `/etc/nginx/ssl/parlaysyndicate.{crt,key}` — self-signed, only Cloudflare sees it |

Ship a change:

```bash
git pull && sudo systemctl restart parlay
sudo journalctl -u parlay -f          # logs
```

Change the nginx block: edit `deploy/nginx/parlaysyndicate`, then
`sudo install -m 644 deploy/nginx/parlaysyndicate /etc/nginx/sites-available/ && sudo nginx -t && sudo systemctl reload nginx`.
Always `nginx -t` first — a bad config would take haneytube.com down with it.

Cloudflare: A records for `parlaysyndicate.com` and `www` point at the VM's
external IP, proxied. The zone also has an **origin rule that sends traffic to
port 8080** — a leftover from when uvicorn listened there directly, and the
cause of the long-running 521. nginx now answers on 8080 as well as 80 and 443,
so the site works whether or not that rule is kept. The app itself listens on
127.0.0.1:8081 so it never competes with nginx for 8080.

### Signing in before an email provider is set up

With `EMAIL_PROVIDER=console`, sign-in links are written to `data/outbox/`
instead of being emailed — and deliberately *not* shown in the browser. Request
a link at /login, then on the box:

```bash
make login-link
```

### Docker (alternative)

`Dockerfile` and `docker-compose.yml` bundle Caddy for a fresh machine. **Don't
use them on parlay-vm**: Caddy needs ports 80 and 443, which nginx already owns.

## Configuration

Everything comes from the environment; see `.env.example`.

| Key | Notes |
|---|---|
| `SECRET_KEY` | required in production |
| `BASE_URL` | used to build sign-in and invite links; `https://` turns on secure cookies |
| `EMAIL_PROVIDER` | `console` (default), `resend`, or `smtp` |
| `SMS_ENABLED` / `TEXTBELT_KEY` | off until a **rotated** key is set |
| `CURRENT_SEASON` | which season the board writes to |
| `SCHEDULER_ENABLED` | background sync/grading |

### Before enabling SMS

The original `send_text.sh` had a live Textbelt key and five phone numbers
committed, and they remain in **git history** even though they're gone from the
working tree. Treat that key as burned and issue a new one. Phone numbers now
live in the `users` table and are edited on the Settings page.

---

## Security notes

The old app wrote form input to a CSV, converted it to a bash config, and ran
`. picks.cfg` — so anything typed into the line field executed as a shell
command, on a page with no login. That path is gone:

- The line field is validated server-side (a number, half-point steps, in range).
- Notifications post over HTTP from Python; nothing reaches a shell.
- Sessions and invites store only SHA-256 hashes; sign-in links are single-use.
- Post-login redirects must be same-site paths.
- Non-members get a 404, not a 403, so syndicate names aren't enumerable.

---

## Data

265 picks across 2023–2025 were recovered from 64 legacy SQLite snapshots and
graded. The counts reconcile with the audit: 90 / 90 / 85.

`scripts/migrate_history.py` is idempotent and reads `db_archive/` read-only,
so it can be re-run from scratch. Keep the archives until the reconciliation
report has been eyeballed once — no single snapshot holds a whole season,
because the old dedup logic deleted rows.
