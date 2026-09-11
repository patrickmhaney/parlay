# Parlay Syndicate — Rebuild Plan

Turning a weekend FastAPI experiment into a real app: automatic grading, three
seasons of recovered history, and syndicates you can invite people into.

- **Reviewed:** `main.py`, `models.py`, `database.py`, `templates/`, `send_text.sh`
- **Data examined:** 63 archived databases in `db_archive/` plus live `bets.db`
- **Verified:** ESPN scoreboard API + an end-to-end grading spike on real picks

> Web version of this document (same content, nicer to read):
> https://claude.ai/code/artifact/d342ad7f-52b1-45e2-ad83-b93317ad9561

---

## Status — built 9 Sep 2026

All six phases are implemented on the `rebuild` branch. 42 tests pass; 265
picks across three seasons are migrated and graded; 1088 games synced.

| Phase | State | Notes |
|---|---|---|
| 0 · Close the hole | done | Injection path gone, key scrubbed from the tree — **still rotate it**, it's in git history |
| 1 · Rebuild history | done | 265/265 matched and graded; reconciles at 90/90/85 |
| 2 · Accounts | done | Magic link, 120-day sessions, syndicates, invites |
| 3 · Pick entry | done | Game-driven, line pre-filled from ESPN, HTMX board |
| 4 · Auto-grading | done | Idempotent sweep + scheduler + manual override |
| 5 · Face lift & stats | done | Tailwind UI, 8 analytics views, CVD-validated chart |
| 6 · Ship it | code written, **not deployed** | Docker/Caddy/backups written but untested — no Docker on the box |

**Needs you before it goes live:**

1. Rotate the Textbelt key, put it in `.env`, set `SMS_ENABLED=true`.
2. Real email addresses for Ben, Hank, Leland and BD
   (`scripts/set_email.py --list`) — they have `.invalid` placeholders.
3. Pick an email provider for magic links (currently `console`).
4. Install Docker, or run `./run.sh` under systemd.

---

## 1. Audit — what the code review turned up

Four findings change what this project is. One of them means we start this week
rather than whenever.

### FIX NOW — The pick form can run commands on the server

The spread/total field is free text (`<input type="text" name="value">`, no
server-side validation). It flows into `output.csv`, then into `picks.cfg` as:

```
Pat="Pat,17,Under,New England Patriots,<your text>"
```

...and `send_text.sh` executes `. picks.cfg` to load it. A value containing a
quote followed by a shell command gets executed by bash as your user. There is
no login on `POST /bet`, so anyone who finds the URL can do it.

Separately: a live Textbelt API key and five real phone numbers are committed in
public git history and should be treated as burned.

### UNLOCK — Auto-grading needs only final scores, and those are free

Because the line is recorded by the player at pick time, grading never needs
historical odds data (the expensive, genuinely hard part). It needs the final
score. ESPN's scoreboard endpoint returns those with no API key:

```
https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2025&seasontype=2&week=16
```

For games that have not kicked off, the same endpoint also returns the current
DraftKings spread and total — so pick entry can pre-fill the line.

### UNLOCK — Three seasons of history are sitting in `db_archive/`

The live `bets.db` gets wiped each season, but the 63 weekly snapshots preserve
everything. Deduplicated by season/week/player, taking the latest snapshot of
each pick:

| Season | Picks | Weeks |
|--------|------:|------:|
| 2023   |    90 |    18 |
| 2024   |    90 |    18 |
| 2025   |    85 |    17 |
| **Total** | **265** | |

All 31 distinct team names in the history match ESPN's `displayName` exactly, so
no alias mapping is required. Every historical pick can be matched to a game and
graded. Day one of the new app has three seasons of records, not zero.

**Read all 63 archives, not just the last one per season.** The intuition that
each season's final snapshot contains that whole season is close but wrong — the
old dedup logic deletes rows, so picks get lost over a season:

| Season | Union of all archives | Last archive only | Lost |
|--------|----------------------:|------------------:|-----:|
| 2023   |                    90 |                81 |    9 |
| 2024   |                    90 |                89 |    1 |
| 2025   |                    85 |                84 |    1 |

Five of the nine 2023 losses are Leland's. Critically, **no two archives ever
disagree** about the same player's pick in the same week — the union is a clean
superset, so merging needs no conflict resolution.

The whole directory is 2.8 MB, and the migration script globs a directory either
way, so there is no cost to using all of them. Once the Phase 1 reconciliation
report checks out, DuckDB becomes the source of truth and the archives can be
deleted outright.

### REWRITE — One background function is doing six jobs

`fetch_bet_data()` in `main.py` deduplicates picks by deleting rows, flips the
`active_flag` state machine, deletes the newest row, copies the whole database
file, writes a CSV, writes a bash config, and shells out to send texts.

Specific problems:

- The delete condition is `week != archived_max + 1 OR week != active_max`.
  `A != x OR A != y` is false only when `x == y == A`, so it deletes the newest
  row in most cases.
- When that delete removes the row that was just inserted, the following
  `bet.active_flag = 'active'` raises `AttributeError` on `None` and is swallowed
  as `print('wrong week')`.
- The group size `5` is hardcoded in two places — this is exactly what blocks
  inviting anyone.
- `.as_scalar()` is deprecated in SQLAlchemy 1.4 and removed in 2.0.

---

## 2. Proof — the grading actually works

Real Week 16 2025 picks from `db_archive/20251229153842_bets.db`, graded against
ESPN final scores. Unmodified output from the spike — no manual lookup:

| Player | Result | Pick          | Final       | Margin vs. line |
|--------|--------|---------------|-------------|----------------:|
| Hank   | WIN    | 49ers -5.5    | 48-27       |          +15.5  |
| Pat    | WIN    | Titans +2.5   | 26-9        |          +19.5  |
| Ben    | LOSS   | Over 40.5     | total 35    |           -5.5  |
| Leland | LOSS   | Lions -6.5    | 24-29       |          -11.5  |
| BD     | LOSS   | Bills -10.5   | 23-20       |           -7.5  |

**Migration note:** across 265 picks nobody has ever picked a Bengals game, so
that team is absent from the historical data. That's on purpose — don't treat it
as a gap in the migration.

---

## 3. Stack — decisions locked

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI | Stays. Restructured into routers / services / repositories. |
| Database | DuckDB, sole store | One file. All writes through one serialized path behind a repository interface. |
| Frontend | Jinja + HTMX + Tailwind | No JS build step, no second server. HTMX replaces the hidden-iframe-and-reload hack. |
| Auth | Email magic link, 120-day session | No passwords. Same token mechanism powers syndicate invites. |
| Hosting | Same box, Dockerized | Docker Compose + Caddy for automatic HTTPS and restart-on-boot. DNS doesn't move. |
| Scores & lines | ESPN scoreboard API | Free, keyless, verified. One adapter module, raw JSON stored. |
| Texts | Textbelt via `httpx` | Same service, called from Python instead of bash. Kills the injection path. |
| Charts | Server-rendered SVG | DuckDB computes, Jinja draws. No chart library, no CDN. |

---

## 4. How a week runs

| When | Step | Notes |
|---|---|---|
| Tue | Schedule syncs | Next week's games and opening lines pulled automatically. |
| Tue–Sun | Picks come in | Pick a game, line pre-fills, adjust if your book differs. Editable until lock. |
| On Nth pick | Board locks, text fires | Threshold is the syndicate's member count, not a hardcoded 5. |
| Sun–Mon | *Everyone places their own bet* | Unchanged. App deep-links to the game in your book. |
| ~~Was: by hand~~ | ~~Look up scores, update records~~ | Gone. |
| Tue 6am | Everything grades itself | Win/loss/push computed, records updated, standings text sent. |

### Grading rules, stated once

- **Spread** — your team's score plus your line versus their score. Positive is a
  win, negative a loss, exactly zero a push.
- **Over** — combined total above your number wins, below loses, equal pushes.
- **Under** — the reverse.

Pushes are tracked as their own outcome rather than folded into wins.

---

## 5. Data model

Today there is one table and no concept of a season, a game, a user, or a result
— which is why the database gets wiped every year and the records live in your
head.

```
users            id, email (unique), display_name, phone, created_at

syndicates       id, name, slug, owner_id -> users, lock_rule
                 (group size becomes a member count, not a constant)

memberships      syndicate_id -> syndicates, user_id -> users, role, joined_at

invites          token_hash, syndicate_id, email, invited_by,
                 expires_at, accepted_at
                 (same token machinery as magic-link login)

games            espn_event_id (unique), season, week,
                 home_team, away_team, kickoff_at,
                 home_score, away_score, status, raw_json
                 (keyed on ESPN team id, not display name)

picks            id, syndicate_id, user_id, game_id -> games,
                 bet_type (SPREAD|OVER|UNDER), side_team, line DECIMAL(4,1),
                 created_at, updated_at
                 (line is a number; edits update, not delete-and-reinsert)

pick_results     pick_id -> picks, outcome (WIN|LOSS|PUSH), margin, graded_at
                 (separate table so re-grading is idempotent and auditable)

sessions         token_hash (never raw), user_id -> users,
                 expires_at (+120 days), created_at, last_seen_at
```

**Why this ends the annual wipe:** `season` is a first-class column on every game
and therefore on every pick. Nothing needs clearing to start a new year — the app
just writes 2026 rows next to the 2025 ones.

---

## 6. The build, in order

Each phase ends with something that works. Sizes assume evening-and-weekend pace.

### Phase 0 — Close the hole, keep the data (~1 evening) — URGENT

Independent of everything else. Do this even if the rebuild stalls.

- [ ] Rotate the Textbelt API key. Assume the committed one is burned.
- [ ] Replace `send_text.sh` with a Python function using `httpx`, key from an
      env var. Removes the command-execution path — nothing gets sourced by bash.
- [ ] Server-side validation on the line field: number between -60 and 60 in
      half-point steps. Reject everything else.
- [ ] `.gitignore` for `venv/`, `__pycache__/`, `nohup.*`, `*.db`, `.env`, `*.swp`.
- [ ] Copy all 63 archives plus `bets.db` off the box before anything touches them.

**Ships:** the current app, still running, no longer executing form input.

### Phase 1 — Rebuild the history (~1 weekend)

Do the data before the app. If the migration surfaces surprises, better to find
them now than after the UI is built on top.

- [ ] DuckDB schema as numbered `.sql` migrations applied at startup against a
      `schema_version` table. No ORM auto-create.
- [ ] ESPN sync: every game for 2023–2026 into `games`, raw JSON stored alongside
      parsed columns.
- [ ] Migration script: read all 63 archives in timestamp order, take the latest
      version of each season/week/player pick, map to a game, load into `picks`.
      Season boundary: archives dated Jan–Feb belong to the *previous* season.
- [ ] Assert the migrated counts are 90 / 90 / 85. Anything lower means the
      archive glob missed files or the season boundary is off by one.
- [ ] Grade all 265 historical picks, write `pick_results`.
- [ ] Print a reconciliation report (matched / unmatched / per-season counts) and
      eyeball it once by hand.
- [ ] **Only after that report checks out:** prune or delete `db_archive/`.

**Ships:** a DuckDB file holding three graded seasons, queryable from the CLI
before any web page exists.

### Phase 2 — Accounts and syndicates (~1 weekend)

The piece that turns "the five of us" into something you can hand to someone else.

- [ ] Magic-link login: request link, click, 120-day session cookie (httponly,
      secure, samesite=lax). Hashed tokens only; single-use, 15-min link expiry.
- [ ] Syndicate creation, invite by email, join via link. Same token code as login.
- [ ] Seed the five of you as real users; backfill every historical pick to the
      right `user_id`.
- [ ] Scope every query by syndicate from the first route — retrofitting
      multi-tenancy later is where this kind of app goes wrong.

**Ships:** real logins, history attached to actual accounts.

### Phase 3 — Pick entry and the weekly ritual (~1 weekend)

Replace the four-dropdown form and the CSV-to-bash pipeline.

- [ ] Game-driven entry: this week's real matchups, DraftKings line pre-filled,
      editable. Two teams that don't play each other becomes unrepresentable.
- [ ] Live board via HTMX — picks appear as entered, no iframe, no timed reload.
- [ ] Edit your own pick until the board locks. An update, not delete-and-reinsert.
- [ ] Lock and notify when member count is reached, driven by the roster.
- [ ] The text message keeps its exact current format. That part isn't broken.

**Ships:** the weekly ritual working end to end on the new stack.

### Phase 4 — Automatic grading (~2 evenings)

The thing that gives you your Tuesday mornings back.

- [ ] Scheduled job polls ESPN for finals, grades every ungraded pick, writes
      results. Idempotent — safe to run twice.
- [ ] Unit tests on grading rules **first**, especially exact pushes and negative
      spreads. This is the code that must never be quietly wrong.
- [ ] Manual override on a result, with a note, for the rare correction.
- [ ] Tuesday standings text: week results + updated leaderboard.

**Ships:** no more manual score lookups, ever.

### Phase 5 — The face lift and the stats (~1–2 weekends)

The part you never got to. Three seasons of graded data are already waiting.

- [ ] Mobile-first Tailwind redesign — this gets read on phones.
- [ ] **Leaderboard:** W-L-P, win rate, units at standard -110, filterable by
      season or all-time.
- [ ] **Cumulative units** line chart per player across the season.
- [ ] **Streaks:** current and longest, wins and losses.
- [ ] **Splits:** spread vs. over vs. under win rate per person; favorites vs.
      underdogs; home vs. away.
- [ ] **Team loyalty:** who rides which teams, and their record doing it.
- [ ] **Weekly winners:** who went 1-0 in weeks where others didn't.
- [ ] **Bad beats:** losses by a half point to a point, ranked.

**Ships:** the app you actually wanted to build.

### Phase 6 — Ship it properly (~1 evening)

Move off `nohup` and a 10MB log file.

- [ ] Dockerfile + Compose, Caddy in front for automatic HTTPS.
- [ ] **Single uvicorn worker** — required by DuckDB's single-writer model.
      Documented in the README so future-you doesn't scale it and wonder why
      writes fail.
- [ ] Nightly backup: DuckDB file copied off-box with a retention window.
      Replaces the copy-the-whole-DB-on-every-pick behaviour.
- [ ] Structured logging to a rotating file, `/health` endpoint, restart-on-failure.

**Ships:** something that survives a reboot without you noticing.

---

## 7. On placing bets from the site

**Don't build this.**

No US sportsbook offers a public bet-placement API. DraftKings and FanDuel have
partner APIs requiring a commercial agreement and licensing; there is no consumer
path. The only technical route is automating their apps against their terms of
service, which realistically ends in closed accounts and frozen balances.

The regulatory side is worse than the technical side. Placing wagers on someone
else's behalf, or pooling money to do it, is the thing gambling licenses exist to
govern — informal arrangements between friends aren't automatically exempt, and it
varies by state. Right now the app is a record keeper: everyone bets their own
money at their own book, and nothing of value moves through the software. That's
a comfortable place to be. Skip money-settlement / "who owes who" features for
the same reason.

**What gets most of the convenience:** deep links. Every major book supports URLs
that open their app directly to a specific game. Once a pick is entered against a
real ESPN game, the board can show a "Place this at DraftKings" button per pick.
Two taps instead of a search. No agreements, no terms violated. Since Phase 3
already links picks to real games, it's an afternoon of work.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **ESPN's API is undocumented** and can change without notice. | All access through one adapter module with a contract test that runs weekly. Raw JSON stored per game, so re-grading never needs the network. |
| **DuckDB allows one writer.** A second uvicorn worker will fail to write. | Single worker, enforced in Compose and the README. All writes through one serialized path behind the repository interface. Read-heavy analytics are unaffected. |
| **The migration mis-attributes a pick** — a mid-week edit read in the wrong order. | Reconciliation report in Phase 1, checked once by hand. Archives are read-only inputs, so the migration can be re-run from scratch. |
| **Grading is subtly wrong** and nobody notices for a month. | Unit tests written before the grader. Every result stores its margin, so a wrong call is visible on the board. |
| **Teams relocate or rebrand** and break historical joins. | Games key on ESPN's stable team id; display names are presentation only. All 31 historical names match today, so this is prevention. |
| **The rebuild stalls mid-season.** | Phase 0 keeps the current app running and safe. Phases 1–2 build alongside without touching it. Nothing switches over until Phase 3 works end to end. |

---

## 9. Still to decide

None of these block starting. Phases 0 and 1 are unaffected by all of them.

- **Email sender.** Magic links need one. Resend or Postmark, both free at this
  volume — needs a DNS record on parlaysyndicate.com. The one external signup
  required.
- **Lock rule.** Today the board locks when the fifth pick lands. Should a pick
  also lock at its own game's kickoff, so a late picker can't see a Thursday
  result first? Probably yes, but it changes the ritual.
- **Push handling in units.** Standard is a push returning the stake — zero units.
  Confirm that matches how you've counted them by hand, or the recovered history
  won't match your memory.
- **The 2026 season.** Week 2 kicks off September 18. Phases 0–3 are comfortable
  before then if you start now; Phase 5's charts can land mid-season.
- **Historical line accuracy.** The migration takes the line you recorded, which
  is what you actually bet — the right number. Worth knowing those are your books'
  lines, not a consensus close.
