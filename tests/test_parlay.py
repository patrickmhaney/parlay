from app.services.parlay import HIT, LIVE, MISSED, PENDING, VOID, Leg, evaluate


def legs(*outcomes):
    return [Leg(f"p{i}", o) for i, o in enumerate(outcomes)]


def test_all_five_win_is_a_hit():
    r = evaluate(legs("WIN", "WIN", "WIN", "WIN", "WIN"))
    assert r.status == HIT and r.goose is None


def test_one_loss_with_four_wins_names_the_goose():
    r = evaluate([Leg("Pat", "WIN"), Leg("Ben", "LOSS"), Leg("Hank", "WIN"),
                  Leg("Leland", "WIN"), Leg("BD", "WIN")])
    assert r.status == MISSED and r.goose == "Ben"


def test_two_losses_means_no_goose():
    r = evaluate(legs("WIN", "LOSS", "LOSS", "WIN", "WIN"))
    assert r.status == MISSED and r.goose is None


def test_a_push_drops_out_so_the_rest_can_still_hit():
    assert evaluate(legs("WIN", "WIN", "PUSH", "WIN", "WIN")).status == HIT


def test_loser_is_still_the_goose_when_another_leg_pushed():
    r = evaluate([Leg("Ben", "LOSS"), Leg("a", "WIN"), Leg("b", "PUSH"), Leg("c", "WIN"), Leg("d", "WIN")])
    assert r.goose == "Ben"


def test_parlay_is_dead_as_soon_as_one_leg_loses():
    r = evaluate(legs("LOSS", None, None, None, None))
    assert r.status == MISSED and r.goose is None     # goose only once everyone's graded


def test_alive_while_nothing_has_lost():
    assert evaluate(legs("WIN", "WIN", None, None, None)).status == LIVE


def test_nothing_graded_yet():
    assert evaluate(legs(None, None, None, None, None)).status == PENDING
    assert evaluate([]).status == PENDING


def test_all_push_is_void():
    assert evaluate(legs("PUSH", "PUSH")).status == VOID
