from datetime import datetime

from app import formatting as f


def test_lines_use_a_true_minus_and_keep_the_plus():
    assert f.line("-3.5") == "\u22123.5"
    assert f.line("3") == "+3"
    assert f.line("3.0") == "+3"
    assert f.line("0") == "PK"
    assert f.line("44.5", signed=False) == "44.5"


def test_kickoff_is_shown_in_eastern_not_utc():
    # 00:15 UTC on a Friday is the Thursday night game at 8:15 PM Eastern.
    assert f.kick(datetime(2026, 9, 11, 0, 15)) == "Thu 8:15 PM"


def test_units_and_record():
    assert f.units(-11.91) == "\u221211.91"
    assert f.units(2.3636) == "+2.36"
    assert f.record(10, 7) == "10\u20137"
    assert f.record(10, 7, 1) == "10\u20137\u20131"


def test_week_date_range():
    assert f.daterange(datetime(2026, 9, 11, 0, 15), datetime(2026, 9, 15, 0, 15)) == "Sep 10 \u2013 14"
    assert f.daterange(datetime(2026, 9, 29, 17), datetime(2026, 10, 3, 17)) == "Sep 29 \u2013 Oct 3"
