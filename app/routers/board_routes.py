"""The weekly board: this week's picks, and entering your own."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Request

from app.config import get_settings
from app.db import get_db
from app.deps import redirect, render, require_syndicate
from app.formatting import line as fmt_line
from app.repositories import games as games_repo
from app.repositories import picks as picks_repo
from app.repositories import stats as stats_repo
from app.repositories import users as users_repo
from app.repositories.users import now as utcnow
from app.services import grading
from app.services.picks_service import PickError, submit_pick, week_is_locked

log = logging.getLogger(__name__)
router = APIRouter()


def _ascii(value) -> str:
    """Line for an <input>: ASCII, signed where it's a spread ('+3', '-3.5')."""
    return fmt_line(value).replace("−", "-").replace("PK", "0")


def _decorate_games(games: list[dict], now) -> list[dict]:
    out = []
    for g in games:
        g = dict(g)
        g["started"] = bool(g.get("kickoff_at") and g["kickoff_at"] <= now)
        bits = []
        if g.get("spread") is not None and g.get("favorite_team_id"):
            fav = g["home_abbr"] if g["favorite_team_id"] == g["home_team_id"] else g["away_abbr"]
            bits.append(f"{fav} {fmt_line(g['spread'])}")
        if g.get("over_under") is not None:
            bits.append(f"O/U {fmt_line(g['over_under'], signed=False)}")
        g["line_hint"] = " · ".join(bits)
        out.append(g)
    return out


def _suggested_line(game: dict, bet_type: str, side_team_id: str | None) -> str:
    """Pre-fill from the book's number. The underdog gets the plus sign."""
    if bet_type in (grading.OVER, grading.UNDER):
        return fmt_line(game["over_under"], signed=False) if game.get("over_under") is not None else ""
    if game.get("spread") is None or not game.get("favorite_team_id") or not side_team_id:
        return ""
    spread = game["spread"]
    return _ascii(spread if side_team_id == game["favorite_team_id"] else -spread)


def _pick_label(p: dict) -> str:
    """'Lions −7' or 'Over 44.5' -- the matchup is shown separately."""
    if p["bet_type"] == grading.SPREAD:
        return f"{p.get('side_short') or p.get('side_name')} {fmt_line(p['line'])}"
    word = "Over" if p["bet_type"] == grading.OVER else "Under"
    return f"{word} {fmt_line(p['line'], signed=False)}"


def _board_context(syn: dict, user: dict, season: int, week: int, *,
                   form: dict | None = None, error: str | None = None,
                   editing: bool = False) -> dict:
    db = get_db()
    now = utcnow()

    games = _decorate_games(games_repo.games_for_week(db, season, week), now)
    picks = picks_repo.picks_for_week(db, syn["id"], season, week)
    for p in picks:
        p["label"] = _pick_label(p)

    members = users_repo.members(db, syn["id"])
    picked = {p["user_id"] for p in picks}
    pending = [m for m in members if m["id"] not in picked]
    my_pick = next((p for p in picks if p["user_id"] == user["id"]), None)

    locked = week_is_locked(db, syn["id"], season, week)
    open_games = [g for g in games if not g["started"]] if syn["lock_at_kickoff"] else games
    can_pick = not locked and bool(open_games)
    # A pick on a game that has kicked off is final for that player.
    if my_pick and syn["lock_at_kickoff"] and my_pick.get("kickoff_at") and my_pick["kickoff_at"] <= now:
        can_pick = False

    form = form or {}
    sel_game_id = (form.get("game_id") or (my_pick and my_pick["game_id"])
                   or (open_games[0]["id"] if open_games else None))
    sel_game = next((g for g in games if g["id"] == sel_game_id), None)
    sel_bet_type = form.get("bet_type") or (my_pick and my_pick["bet_type"]) or grading.SPREAD
    sel_side = form.get("side_team_id") or (my_pick and my_pick["side_team_id"])
    if sel_game and sel_bet_type == grading.SPREAD and sel_side not in (
            sel_game["home_team_id"], sel_game["away_team_id"]):
        sel_side = sel_game["away_team_id"]

    sel_line = form.get("line")
    if sel_line is None:
        if (my_pick and my_pick["game_id"] == sel_game_id
                and my_pick["bet_type"] == sel_bet_type
                and (sel_bet_type != grading.SPREAD or my_pick["side_team_id"] == sel_side)):
            sel_line = (_ascii(my_pick["line"]) if sel_bet_type == grading.SPREAD
                        else fmt_line(my_pick["line"], signed=False))
        else:
            sel_line = _suggested_line(sel_game, sel_bet_type, sel_side) if sel_game else ""

    kickoffs = [g["kickoff_at"] for g in games if g.get("kickoff_at")]
    parlay = stats_repo.week_parlay(db, syn["id"], season, week) if picks else None

    return {
        "syndicate": syn, "season": season, "week": week,
        "games": games, "picks": picks, "pending": pending, "my_pick": my_pick,
        "member_count": len(members),
        "sel_game_id": sel_game_id, "sel_game": sel_game,
        "sel_bet_type": sel_bet_type, "sel_side": sel_side, "sel_line": sel_line,
        "locked": locked, "can_pick": can_pick,
        "show_form": can_pick and (editing or error is not None or my_pick is None),
        "editing": editing and my_pick is not None,
        "week_start": min(kickoffs) if kickoffs else None,
        "week_end": max(kickoffs) if kickoffs else None,
        "parlay": parlay,
        "error": error, "active_nav": "board",
    }


@router.get("/s/{slug}", name="board")
def board(request: Request, slug: str, week: int | None = None, season: int | None = None):
    user, syn = require_syndicate(request, slug)
    db = get_db()
    season = season or get_settings().current_season
    week = week or games_repo.current_week(db, season)

    ctx = _board_context(syn, user, season, week)
    weeks = [r["week"] for r in db.rows(
        "SELECT DISTINCT week FROM games WHERE season = ? ORDER BY week", [season])] or [1]
    ctx["all_weeks"] = weeks
    ctx["standings"] = [r for r in stats_repo.leaderboard(db, syn["id"], season) if r["graded"]]
    return render(request, "board.html", ctx)


@router.get("/s/{slug}/week/{week}", name="board_week")
def board_week(request: Request, slug: str, week: int, season: int | None = None):
    q = f"?week={week}" + (f"&season={season}" if season else "")
    return redirect(f"/s/{slug}{q}")


@router.get("/s/{slug}/pick-form", name="pick_form_partial")
def pick_form_partial(
    request: Request, slug: str, week: int, season: int | None = None,
    game_id: str = "", bet_type: str = "", side_team_id: str = "", edit: int = 0,
):
    """HTMX: re-render the panel when the game or bet type changes, or when
    Edit / Cancel is pressed."""
    user, syn = require_syndicate(request, slug)
    season = season or get_settings().current_season
    form = {"game_id": game_id or None, "bet_type": bet_type or None,
            "side_team_id": side_team_id or None}
    ctx = _board_context(syn, user, season, week, form=form, editing=bool(edit))
    return render(request, "partials/pick_panel.html", ctx)


@router.post("/s/{slug}/pick", name="submit_pick_route")
def submit_pick_route(
    request: Request, slug: str, week: int = Form(...), game_id: str = Form(...),
    bet_type: str = Form(...), line: str = Form(""), side_team_id: str = Form(""),
    season: int | None = Form(None),
):
    user, syn = require_syndicate(request, slug)
    season = season or get_settings().current_season
    error = None
    try:
        submit_pick(
            get_db(), syndicate_id=syn["id"], user_id=user["id"], game_id=game_id,
            season=season, week=week, bet_type=bet_type, raw_line=line,
            side_team_id=side_team_id or None,
        )
    except PickError as exc:
        error = str(exc)
    except Exception:
        log.exception("pick submission failed")
        error = "Couldn't save that pick. Try again."

    form = None if error is None else {
        "game_id": game_id, "bet_type": bet_type,
        "side_team_id": side_team_id or None, "line": line,
    }
    ctx = _board_context(syn, user, season, week, form=form, error=error)
    return render(request, "partials/pick_panel.html", ctx)
