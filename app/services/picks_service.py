"""Business rules around entering, locking and grading picks."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.config import get_settings
from app.db import Database
from app.repositories import games as games_repo
from app.repositories import picks as picks_repo
from app.repositories import users as users_repo
from app.services import grading, notify

log = logging.getLogger(__name__)

MIN_LINE = Decimal("-60")
MAX_LINE = Decimal("60")
MIN_TOTAL = Decimal("20")
MAX_TOTAL = Decimal("100")


class PickError(ValueError):
    """A pick that cannot be accepted, with a message safe to show the user."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_line(raw: str, bet_type: str) -> Decimal:
    """Server-side validation of the one free-text field in the app.

    The legacy version accepted anything and passed it to bash. This accepts a
    number in half-point steps, in a plausible range, and nothing else.
    """
    if raw is None:
        raise PickError("Enter a number for the line.")
    text = str(raw).strip().replace("\u2212", "-").replace("+", "")
    if not text:
        raise PickError("Enter a number for the line.")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise PickError("Enter the line as a number, like -3.5.")
    if value != value.quantize(Decimal("0.1")):
        raise PickError("Use half points, like -3.5 or 44.")
    if (value * 2) != (value * 2).to_integral_value():
        raise PickError("Use half points, like -3.5 or 44.")
    if bet_type == grading.SPREAD:
        if not (MIN_LINE <= value <= MAX_LINE):
            raise PickError(f"A spread should be between {MIN_LINE} and {MAX_LINE}.")
    else:
        if not (MIN_TOTAL <= value <= MAX_TOTAL):
            raise PickError(f"A total should be between {MIN_TOTAL} and {MAX_TOTAL}.")
    return value


def pick_summary(pick: dict) -> str:
    """'Jaguars -4.5' or 'Under 41.5 Patriots/Jets'."""
    return grading.describe(
        bet_type=pick["bet_type"],
        line=pick["line"],
        side_team_name=pick.get("side_short") or pick.get("side_name"),
        home_team_name=pick.get("home_short") or pick.get("home_name") or "",
        away_team_name=pick.get("away_short") or pick.get("away_name") or "",
    )


def week_is_locked(db: Database, syndicate_id: str, season: int, week: int) -> bool:
    return picks_repo.get_week_lock(db, syndicate_id, season, week) is not None


def submit_pick(
    db: Database, *, syndicate_id: str, user_id: str, game_id: str, season: int,
    week: int, bet_type: str, raw_line: str, side_team_id: str | None,
) -> dict:
    """Validate and store one pick, then lock+notify if the board is complete."""
    if bet_type not in grading.BET_TYPES:
        raise PickError("Choose a bet type.")

    game = games_repo.get_game(db, game_id)
    if not game:
        raise PickError("That game is no longer available.")
    if game["season"] != season or game["week"] != week:
        raise PickError("That game is not in this week.")

    if bet_type == grading.SPREAD:
        if side_team_id not in (game["home_team_id"], game["away_team_id"]):
            raise PickError("Pick one of the two teams in that game.")
    else:
        side_team_id = None

    line = parse_line(raw_line, bet_type)

    syn = users_repo.get_syndicate(db, syndicate_id)
    if week_is_locked(db, syndicate_id, season, week):
        raise PickError("Picks are locked for this week.")
    if syn and syn["lock_at_kickoff"] and game["kickoff_at"] and game["kickoff_at"] <= _now():
        raise PickError("That game has already kicked off.")

    pick_id = picks_repo.upsert_pick(
        db, syndicate_id=syndicate_id, user_id=user_id, game_id=game_id,
        season=season, week=week, bet_type=bet_type, line=line,
        side_team_id=side_team_id,
    )
    maybe_lock_and_notify(db, syndicate_id, season, week)
    return picks_repo.get_pick(db, pick_id)


def maybe_lock_and_notify(db: Database, syndicate_id: str, season: int, week: int) -> bool:
    """When every member has a pick in, lock the board and send the text once.

    The threshold is the syndicate's member count -- not a hardcoded 5, which
    is what made the old app impossible to share.
    """
    members = users_repo.members(db, syndicate_id)
    picks = picks_repo.picks_for_week(db, syndicate_id, season, week)
    if not members or len(picks) < len(members):
        return False
    if not picks_repo.lock_week(db, syndicate_id, season, week):
        return False  # someone else already locked it

    settings = get_settings()
    rows = [{"display_name": p["display_name"], "summary": pick_summary(p)} for p in picks]
    message = notify.picks_are_in_message(rows, settings.base_url)
    for m in members:
        if m.get("phone"):
            notify.send_sms(db, m["phone"], message, "picks_in", syndicate_id)
    picks_repo.mark_notified(db, syndicate_id, season, week)
    log.info("locked %s %s week %s and notified %s members",
             syndicate_id, season, week, len(members))
    return True


def grade_pending(db: Database, syndicate_id: str | None = None) -> dict:
    """Grade every pick whose game is final. Idempotent."""
    graded, failed = 0, []
    for p in picks_repo.ungraded_picks(db, syndicate_id):
        try:
            res = grading.grade(
                bet_type=p["bet_type"], line=p["line"],
                home_team_id=p["home_team_id"], away_team_id=p["away_team_id"],
                home_score=p["home_score"], away_score=p["away_score"],
                side_team_id=p["side_team_id"],
            )
        except grading.GradingError as exc:
            failed.append({"pick_id": p["id"], "error": str(exc)})
            log.error("could not grade pick %s: %s", p["id"], exc)
            continue
        picks_repo.save_result(db, p["id"], res.outcome, res.margin)
        graded += 1
    return {"graded": graded, "failed": failed}


def override_result(
    db: Database, pick_id: str, outcome: str, note: str | None = None
) -> None:
    if outcome not in (grading.WIN, grading.LOSS, grading.PUSH):
        raise PickError("Outcome must be WIN, LOSS or PUSH.")
    pick = picks_repo.get_pick(db, pick_id)
    if not pick:
        raise PickError("No such pick.")
    margin = pick.get("margin") or Decimal("0")
    picks_repo.save_result(db, pick_id, outcome, margin, manual_override=True, note=note)
