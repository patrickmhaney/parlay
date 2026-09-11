"""The grading rules are the one place a silent bug would corrupt years of
records, so every branch is pinned down here -- especially exact pushes."""
from decimal import Decimal

import pytest

from app.services.grading import (
    GradingError,
    LOSS,
    PUSH,
    WIN,
    describe,
    format_line,
    grade,
    units_for,
)

HOME, AWAY = "home1", "away1"


def g(bet_type, line, hs, as_, side=None):
    return grade(
        bet_type=bet_type,
        line=line,
        home_team_id=HOME,
        away_team_id=AWAY,
        home_score=hs,
        away_score=as_,
        side_team_id=side,
    )


# --- spreads ---------------------------------------------------------------

def test_favorite_covers():
    # home wins 48-27 laying 5.5 -> covers by 15.5
    r = g("SPREAD", "-5.5", 48, 27, side=HOME)
    assert r.outcome == WIN and r.margin == Decimal("15.5")


def test_favorite_fails_to_cover_but_wins_game():
    # Bills win 23-20 but were laying 10.5
    r = g("SPREAD", "-10.5", 23, 20, side=HOME)
    assert r.outcome == LOSS and r.margin == Decimal("-7.5")


def test_underdog_covers_while_losing():
    # Titans +2.5 lose 26-9? no: they won outright, still a cover
    r = g("SPREAD", "+2.5", 9, 26, side=AWAY)
    assert r.outcome == WIN and r.margin == Decimal("19.5")


def test_underdog_covers_by_losing_close():
    # away loses 20-17 but had +3.5
    r = g("SPREAD", "3.5", 20, 17, side=AWAY)
    assert r.outcome == WIN and r.margin == Decimal("0.5")


def test_spread_exact_push():
    # away loses by exactly 3 with +3
    r = g("SPREAD", "3", 20, 17, side=AWAY)
    assert r.outcome == PUSH and r.margin == Decimal("0")


def test_spread_push_on_the_favorite():
    r = g("SPREAD", "-7", 21, 14, side=HOME)
    assert r.outcome == PUSH and r.margin == Decimal("0")


def test_pickem_zero_line():
    assert g("SPREAD", "0", 21, 20, side=HOME).outcome == WIN
    assert g("SPREAD", "0", 20, 21, side=HOME).outcome == LOSS
    assert g("SPREAD", "0", 20, 20, side=HOME).outcome == PUSH


def test_spread_requires_a_side():
    with pytest.raises(GradingError):
        g("SPREAD", "-3", 21, 14)


def test_spread_side_must_be_in_the_game():
    with pytest.raises(GradingError):
        g("SPREAD", "-3", 21, 14, side="someone_else")


# --- totals ----------------------------------------------------------------

def test_over_wins():
    r = g("OVER", "41.5", 24, 21)  # 45
    assert r.outcome == WIN and r.margin == Decimal("3.5")


def test_over_loses():
    r = g("OVER", "40.5", 20, 15)  # 35
    assert r.outcome == LOSS and r.margin == Decimal("-5.5")


def test_under_wins():
    r = g("UNDER", "51.5", 20, 15)  # 35
    assert r.outcome == WIN and r.margin == Decimal("16.5")


def test_under_loses():
    r = g("UNDER", "41.5", 24, 21)  # 45
    assert r.outcome == LOSS and r.margin == Decimal("-3.5")


def test_total_exact_push_both_directions():
    assert g("OVER", "45", 24, 21).outcome == PUSH
    assert g("UNDER", "45", 24, 21).outcome == PUSH


def test_shutout_zero_total_under():
    r = g("UNDER", "30", 0, 0)
    assert r.outcome == WIN and r.margin == Decimal("30")


# --- guards ----------------------------------------------------------------

def test_ungraded_without_scores():
    with pytest.raises(GradingError):
        g("OVER", "41.5", None, 21)


def test_unknown_bet_type():
    with pytest.raises(GradingError):
        g("PARLAY", "1", 10, 10)


# --- units -----------------------------------------------------------------

def test_units_at_standard_juice():
    assert units_for(WIN, -110) == Decimal(100) / Decimal(110)
    assert units_for(LOSS, -110) == Decimal("-1")
    assert units_for(PUSH, -110) == Decimal("0")


def test_units_at_plus_money():
    assert units_for(WIN, +150) == Decimal("1.5")


def test_a_week_of_one_and_four_is_net_negative():
    # 1-4 at -110 is the shape of a bad week; it must not round to break-even.
    net = units_for(WIN) + 4 * units_for(LOSS)
    assert net < Decimal("-3")


# --- formatting ------------------------------------------------------------

def test_format_line_signs():
    assert format_line("-4.5") == "-4.5"
    assert format_line("3") == "+3"
    assert format_line("6.5") == "+6.5"
    assert format_line("0") == "0"


def test_describe_reads_like_the_text_message():
    assert describe(bet_type="SPREAD", line="-4.5", side_team_name="Jaguars") == "Jaguars -4.5"
    assert describe(
        bet_type="UNDER", line="41.5",
        home_team_name="Jets", away_team_name="Patriots",
    ) == "Under 41.5 Patriots/Jets"
