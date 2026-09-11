"""Background jobs: pull scores, grade picks, send the results text.

Runs in-process on APScheduler. Because DuckDB takes a single writer and the
app runs one worker, these jobs share the same write lock as the request path.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db import get_db
from app.repositories import picks as picks_repo
from app.repositories import users as users_repo
from app.services import notify, sync
from app.services.espn import EspnClient
from app.services.picks_service import grade_pending, pick_summary

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def sync_job() -> None:
    """Refresh schedule/odds/scores for weeks that aren't finished."""
    settings = get_settings()
    db = get_db()
    client = EspnClient(settings.espn_cache_dir)
    try:
        n = sync.sync_live_weeks(db, client, settings.current_season)
        log.info("scheduled sync refreshed %s games", n)
    except Exception:
        log.exception("scheduled sync failed")


def grade_job() -> None:
    """Grade everything gradable, then text each syndicate its week's results."""
    settings = get_settings()
    db = get_db()
    try:
        sync_job()
        result = grade_pending(db)
        log.info("scheduled grading: %s", result)
        if result["graded"]:
            _send_results(db, settings)
    except Exception:
        log.exception("scheduled grading failed")


def _send_results(db, settings) -> None:
    """One text per syndicate for the most recent fully-graded week."""
    for syn in db.rows("SELECT * FROM syndicates"):
        row = db.row(
            """SELECT p.season, p.week
               FROM picks p JOIN pick_results r ON r.pick_id = p.id
               WHERE p.syndicate_id = ?
               GROUP BY p.season, p.week
               HAVING COUNT(*) = (SELECT COUNT(*) FROM picks p2
                                  WHERE p2.syndicate_id = p.syndicate_id
                                    AND p2.season = p.season AND p2.week = p.week)
               ORDER BY p.season DESC, p.week DESC LIMIT 1""",
            [syn["id"]],
        )
        if not row:
            continue
        season, week = row["season"], row["week"]
        lock = picks_repo.get_week_lock(db, syn["id"], season, week)
        if lock and lock.get("notified_at") is None:
            continue  # the "picks are in" text hasn't even gone out

        already = db.value(
            """SELECT 1 FROM notifications
               WHERE syndicate_id = ? AND kind = 'results'
                 AND body LIKE ? AND status = 'sent' LIMIT 1""",
            [syn["id"], f"Week {week} results:%"],
        )
        if already:
            continue

        picks = picks_repo.picks_for_week(db, syn["id"], season, week)
        rows = [{"display_name": p["display_name"], "outcome": p["outcome"] or "?",
                 "summary": pick_summary(p)} for p in picks if p["outcome"]]
        if not rows:
            continue
        message = notify.results_message(week, rows, settings.base_url)
        for m in users_repo.members(db, syn["id"]):
            if m.get("phone"):
                notify.send_sms(db, m["phone"], message, "results", syn["id"])


def cleanup_job() -> None:
    try:
        users_repo.purge_expired(get_db())
    except Exception:
        log.exception("cleanup failed")


def start() -> BackgroundScheduler | None:
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled or _scheduler is not None:
        return _scheduler

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        grade_job, CronTrigger(hour=settings.grade_cron_hour,
                               minute=settings.grade_cron_minute),
        id="grade", replace_existing=True,
    )
    sched.add_job(
        sync_job, CronTrigger(hour=settings.sync_cron_hour,
                              minute=settings.sync_cron_minute),
        id="sync", replace_existing=True,
    )
    # During the season, games finish at all hours; a light hourly pass keeps
    # the board current without hammering ESPN.
    sched.add_job(sync_job, CronTrigger(minute=17), id="sync_hourly", replace_existing=True)
    sched.add_job(cleanup_job, CronTrigger(hour=4, minute=0), id="cleanup", replace_existing=True)
    sched.start()
    _scheduler = sched
    log.info("scheduler started: grade %02d:%02d UTC, sync %02d:%02d UTC",
             settings.grade_cron_hour, settings.grade_cron_minute,
             settings.sync_cron_hour, settings.sync_cron_minute)
    return sched


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
