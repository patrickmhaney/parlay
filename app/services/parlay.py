"""The weekly parlay: every member's pick is one leg of a single shared bet.

Rules (standard sportsbook parlay rules):
  * Any losing leg sinks the parlay -- it's MISSED as soon as one leg loses,
    even before the others are graded.
  * A pushed leg drops out; the parlay pays on the remaining legs. So the
    parlay HITS when every leg is graded, none lost, and at least one won.
  * If every leg pushes, the parlay is VOID (stake returned).
  * Otherwise, while legs are still ungraded and none has lost, it's LIVE.

The goose: the one member whose leg lost when every other leg won or pushed
-- the only thing standing between the group and a hit.
"""
from __future__ import annotations

from dataclasses import dataclass

HIT, MISSED, LIVE, VOID, PENDING = "HIT", "MISSED", "LIVE", "VOID", "PENDING"


@dataclass(frozen=True)
class Leg:
    name: str
    outcome: str | None        # WIN / LOSS / PUSH, or None if not graded yet


@dataclass(frozen=True)
class ParlayResult:
    status: str
    legs: int
    won: int
    lost: int
    pushed: int
    pending: int
    goose: str | None


def evaluate(legs: list[Leg]) -> ParlayResult:
    won = sum(1 for l in legs if l.outcome == "WIN")
    lost = sum(1 for l in legs if l.outcome == "LOSS")
    pushed = sum(1 for l in legs if l.outcome == "PUSH")
    pending = sum(1 for l in legs if l.outcome is None)

    if not legs:
        status = PENDING
    elif lost:
        status = MISSED
    elif pending:
        status = LIVE if (won or pushed) else PENDING
    elif won:
        status = HIT
    else:
        status = VOID

    # A goose needs company: one loser, everyone else graded and not losing.
    goose = None
    if lost == 1 and pending == 0 and len(legs) >= 2:
        goose = next(l.name for l in legs if l.outcome == "LOSS")

    return ParlayResult(status, len(legs), won, lost, pushed, pending, goose)
