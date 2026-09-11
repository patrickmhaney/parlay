"""Bet grading. Pure functions, no database, no network.

"Grading" is the sportsbook term for settling a bet: deciding win / loss / push
once the game is final.

Because each player records the line they actually took at pick time, grading
never needs historical odds -- only the final score.

Rules
-----
SPREAD  your team's score + your line, versus their score.
        > 0 win, < 0 loss, exactly 0 push.
OVER    combined total above your number wins, below loses, equal pushes.
UNDER   the reverse.

`margin` is always signed so that positive means "covered by this much" -- it
reads the same for all three bet types, which is what the UI and the bad-beat
report rely on.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

SPREAD = "SPREAD"
OVER = "OVER"
UNDER = "UNDER"
BET_TYPES = (SPREAD, OVER, UNDER)

WIN = "WIN"
LOSS = "LOSS"
PUSH = "PUSH"


class GradingError(ValueError):
    """Raised when a pick cannot be graded from the data supplied."""


@dataclass(frozen=True)
class GradeResult:
    outcome: str
    margin: Decimal


def _dec(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _outcome(margin: Decimal) -> str:
    if margin > 0:
        return WIN
    if margin < 0:
        return LOSS
    return PUSH


def grade(
    *,
    bet_type: str,
    line,
    home_team_id: str,
    away_team_id: str,
    home_score: int | None,
    away_score: int | None,
    side_team_id: str | None = None,
) -> GradeResult:
    """Grade one pick. Raises GradingError if it cannot be settled."""
    if bet_type not in BET_TYPES:
        raise GradingError(f"unknown bet type {bet_type!r}")
    if home_score is None or away_score is None:
        raise GradingError("game has no final score")

    line = _dec(line)
    home_score = int(home_score)
    away_score = int(away_score)

    if bet_type == SPREAD:
        if side_team_id is None:
            raise GradingError("spread pick has no side")
        if side_team_id == home_team_id:
            mine, theirs = home_score, away_score
        elif side_team_id == away_team_id:
            mine, theirs = away_score, home_score
        else:
            raise GradingError(
                f"side {side_team_id!r} is not in this game "
                f"({away_team_id} @ {home_team_id})"
            )
        margin = _dec(mine) + line - _dec(theirs)
        return GradeResult(_outcome(margin), margin)

    total = _dec(home_score + away_score)
    if bet_type == OVER:
        margin = total - line
    else:  # UNDER
        margin = line - total
    return GradeResult(_outcome(margin), margin)


# --- description helpers ---------------------------------------------------


def format_line(line) -> str:
    """-4.5 -> '-4.5', 3.0 -> '+3', 41.5 -> '41.5' (sign only where meaningful)."""
    d = _dec(line).normalize()
    s = format(d, "f")
    if d > 0:
        s = "+" + s
    return s


def describe(
    *,
    bet_type: str,
    line,
    side_team_name: str | None = None,
    home_team_name: str = "",
    away_team_name: str = "",
) -> str:
    """One-line human description, used in the board and the text message."""
    d = _dec(line).normalize()
    total = format(d, "f")
    if bet_type == SPREAD:
        return f"{side_team_name} {format_line(line)}"
    matchup = f"{away_team_name}/{home_team_name}" if home_team_name else ""
    label = "Over" if bet_type == OVER else "Under"
    return f"{label} {total} {matchup}".strip()
