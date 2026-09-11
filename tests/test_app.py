"""End-to-end coverage of the flows a member actually uses."""
from __future__ import annotations

from tests.conftest import AWAY, GAME_ID, HOME, SEASON, WEEK, game_id, login


# --- auth ------------------------------------------------------------------

def test_landing_page_renders_for_anonymous(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'name="email"' in r.text          # the root page is sign-in itself


def test_board_requires_login(client, people):
    r = client.get(f"/s/{people['syndicate']['slug']}", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_magic_link_signs_you_in(client, db, people):
    login(client, db, "owner@example.com")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert people["syndicate"]["slug"] in r.headers["location"]


def test_login_token_is_single_use(client, db):
    from app.services import auth
    link = auth.issue_login_link(db, "owner@example.com", None)
    token = link.split("token=")[1]
    assert client.get("/auth/verify", params={"token": token},
                      follow_redirects=False).status_code == 303
    second = client.get("/auth/verify", params={"token": token}, follow_redirects=False)
    assert second.status_code == 400


def test_bad_token_is_rejected(client):
    r = client.get("/auth/verify", params={"token": "nope"}, follow_redirects=False)
    assert r.status_code == 400


def test_login_redirect_cannot_leave_the_site(client, db):
    """A stored redirect must be a same-site path, never an absolute URL."""
    from app.services import auth
    link = auth.issue_login_link(db, "owner@example.com", "https://evil.example.com/x")
    token = link.split("token=")[1]
    r = client.get("/auth/verify", params={"token": token}, follow_redirects=False)
    assert r.status_code == 303
    assert not r.headers["location"].startswith("http")


# --- membership scoping ----------------------------------------------------

def test_non_member_cannot_see_a_syndicate(client, db, people):
    from app.repositories import users as users_repo
    users_repo.get_or_create_user(db, "stranger@example.com", "Stranger")
    login(client, db, "stranger@example.com")
    r = client.get(f"/s/{people['syndicate']['slug']}")
    assert r.status_code == 404


# --- the board -------------------------------------------------------------

def test_board_renders_with_the_pick_form(client, db, people):
    login(client, db, "owner@example.com")
    r = client.get(f"/s/{people['syndicate']['slug']}", params={"week": WEEK})
    assert r.status_code == 200
    assert "Your pick" in r.text
    assert "AWY @ HOM" in r.text


def test_line_is_prefilled_from_the_book(client, db, people):
    login(client, db, "owner@example.com")
    r = client.get(f"/s/{people['syndicate']['slug']}/pick-form",
                   params={"week": WEEK, "game_id": GAME_ID,
                           "bet_type": "OVER"})
    assert r.status_code == 200
    assert 'value="44.5"' in r.text


def test_submitting_a_pick_shows_it_on_the_board(client, db, people):
    login(client, db, "owner@example.com")
    r = client.post(f"/s/{people['syndicate']['slug']}/pick", data={
        "week": WEEK, "game_id": GAME_ID, "bet_type": "SPREAD",
        "side_team_id": HOME, "line": "-3.5",
    })
    assert r.status_code == 200
    assert "Owner" in r.text
    assert "Herons \u22123.5" in r.text


def test_a_junk_line_is_rejected_not_executed(client, db, people):
    """The exact payload that would have run a shell command in the old app."""
    login(client, db, "owner@example.com")
    r = client.post(f"/s/{people['syndicate']['slug']}/pick", data={
        "week": WEEK, "game_id": GAME_ID, "bet_type": "SPREAD",
        "side_team_id": HOME, "line": 'x";touch /tmp/pwned;"',
    })
    assert r.status_code == 200
    assert "Enter the line as a number" in r.text


def test_resubmitting_replaces_rather_than_duplicates(client, db, people):
    login(client, db, "owner@example.com")
    slug = people["syndicate"]["slug"]
    for line in ("-3.5", "-6.5"):
        client.post(f"/s/{slug}/pick", data={
            "week": WEEK, "game_id": GAME_ID, "bet_type": "SPREAD",
            "side_team_id": HOME, "line": line,
        })
    n = db.value(
        """SELECT COUNT(*) FROM picks WHERE syndicate_id = ? AND season = ? AND week = ?""",
        [people["syndicate"]["id"], SEASON, WEEK],
    )
    assert n == 1
    line = db.value(
        "SELECT line FROM picks WHERE syndicate_id = ? AND week = ?",
        [people["syndicate"]["id"], WEEK],
    )
    assert float(line) == -6.5


def test_board_locks_once_everyone_is_in(client, db, people):
    """The threshold is the member count, not a hardcoded 5."""
    from app.repositories import picks as picks_repo
    slug = people["syndicate"]["slug"]
    sid = people["syndicate"]["id"]
    week = 3

    login(client, db, "owner@example.com")
    client.post(f"/s/{slug}/pick", data={
        "week": week, "game_id": game_id(week), "bet_type": "SPREAD",
        "side_team_id": HOME, "line": "-3.5"})
    assert picks_repo.get_week_lock(db, sid, SEASON, week) is None

    login(client, db, "friend@example.com")
    r = client.post(f"/s/{slug}/pick", data={
        "week": week, "game_id": game_id(week), "bet_type": "OVER", "line": "44.5"})
    assert r.status_code == 200
    assert picks_repo.get_week_lock(db, sid, SEASON, week) is not None
    assert 'data-state="locked"' in r.text


def test_cannot_pick_a_team_that_is_not_in_the_game(client, db, people):
    login(client, db, "owner@example.com")
    r = client.post(f"/s/{people['syndicate']['slug']}/pick", data={
        "week": 4, "game_id": game_id(4), "bet_type": "SPREAD",
        "side_team_id": "999", "line": "-3.5",
    })
    assert "Pick one of the two teams" in r.text


# --- grading ---------------------------------------------------------------

def test_grading_flows_through_to_the_board(client, db, people):
    from app.services.picks_service import grade_pending
    slug, sid = people["syndicate"]["slug"], people["syndicate"]["id"]
    week = 5

    login(client, db, "owner@example.com")
    client.post(f"/s/{slug}/pick", data={
        "week": week, "game_id": game_id(week), "bet_type": "SPREAD",
        "side_team_id": HOME, "line": "-3.5"})

    db.execute(
        """UPDATE games SET home_score = 27, away_score = 20,
               completed = TRUE, status = 'STATUS_FINAL' WHERE id = ?""",
        [game_id(week)],
    )
    out = grade_pending(db, sid)
    assert out["graded"] >= 1
    assert not out["failed"]

    r = client.get(f"/s/{slug}", params={"week": week})
    assert 'data-outcome="WIN"' in r.text


# --- pages -----------------------------------------------------------------

def test_stats_page_renders(client, db, people):
    login(client, db, "owner@example.com")
    r = client.get(f"/s/{people['syndicate']['slug']}/stats")
    assert r.status_code == 200
    assert "Standings" in r.text


def test_settings_page_renders(client, db, people):
    login(client, db, "owner@example.com")
    r = client.get(f"/s/{people['syndicate']['slug']}/settings")
    assert r.status_code == 200
    assert 'id="invite"' in r.text


def test_non_owner_cannot_invite(client, db, people):
    login(client, db, "friend@example.com")
    r = client.post(f"/s/{people['syndicate']['slug']}/invite",
                    data={"email": "x@example.com"})
    assert r.status_code == 403


def test_invite_round_trip_adds_a_member(client, db, people):
    from app.repositories import users as users_repo
    from app.services import auth
    sid = people["syndicate"]["id"]
    before = users_repo.member_count(db, sid)

    link = auth.issue_invite_link(db, sid, "newcomer@example.com", people["owner"]["id"])
    token = link.rsplit("/", 1)[1]

    login(client, db, "newcomer@example.com")
    assert client.get(f"/invite/{token}").status_code == 200
    r = client.post(f"/invite/{token}", follow_redirects=False)
    assert r.status_code == 303
    assert users_repo.member_count(db, sid) == before + 1


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_page_never_shows_the_link_outside_debug(client):
    """With the console email provider, the link must not be echoed to the
    browser unless DEBUG is on -- otherwise anyone could type any member's
    email address and be handed a login to their account."""
    r = client.post("/login", data={"email": "owner@example.com"})
    assert r.status_code == 200
    assert "Check your email" in r.text
    assert "/auth/verify?token=" not in r.text


def test_owner_can_change_a_members_email(client, db, people):
    """DuckDB 1.1.x rejected UPDATEs to a UNIQUE column as a false primary-key
    violation, which broke this form (and scripts/set_email.py)."""
    login(client, db, "owner@example.com")
    friend = people["friend"]
    r = client.post(f"/s/{people['syndicate']['slug']}/members",
                    data={"user_id": friend["id"], "email": "friend.new@example.com", "phone": ""},
                    follow_redirects=False)
    assert r.status_code == 303
    assert db.value("SELECT email FROM users WHERE id = ?", [friend["id"]]) == "friend.new@example.com"
    # put it back for the other tests
    db.execute("UPDATE users SET email = 'friend@example.com' WHERE id = ?", [friend["id"]])



# --- design cleanup regressions -------------------------------------------

def test_members_without_a_pick_are_listed(client, db, people):
    login(client, db, "owner@example.com")
    from app.repositories import users as users_repo
    r = client.get(f"/s/{people['syndicate']['slug']}", params={"week": 6})
    # nobody has picked week 6, so every member is listed as pending
    assert r.text.count("data-pending") == users_repo.member_count(db, people["syndicate"]["id"])


def test_underdog_prefill_keeps_its_plus_sign(client, db, people):
    """Home is the -3.5 favourite, so the away side must pre-fill as +3.5 --
    it used to show a bare 3.5, which reads as the favourite's number."""
    login(client, db, "owner@example.com")
    r = client.get(f"/s/{people['syndicate']['slug']}/pick-form",
                   params={"week": 6, "game_id": game_id(6), "bet_type": "SPREAD",
                           "side_team_id": AWAY})
    assert 'value="+3.5"' in r.text


def test_clicking_your_name_no_longer_signs_you_out(client, db, people):
    login(client, db, "owner@example.com")
    board = client.get(f"/s/{people['syndicate']['slug']}")
    assert 'action="/logout"' not in board.text
    settings = client.get(f"/s/{people['syndicate']['slug']}/settings")
    assert 'action="/logout"' in settings.text


def test_no_feature_copy_or_emoji_on_any_page(client, db, people):
    """The old UI explained itself on every screen. Keep it from creeping back."""
    banned = ["pre-filled", "DraftKings", "via ESPN", "Be first", "The text goes out",
              "Half-point", "No password", "\U0001F3C8", "&#127944;", "Units", "Juice"]
    slug = people["syndicate"]["slug"]
    pages = [client.get("/").text]
    login(client, db, "owner@example.com")
    for path in (f"/s/{slug}", f"/s/{slug}/stats", f"/s/{slug}/settings"):
        pages.append(client.get(path).text)
    for html in pages:
        for phrase in banned:
            assert phrase not in html, phrase


def test_stats_empty_state_for_a_new_syndicate(client, db):
    from app.repositories import users as users_repo
    u = users_repo.get_or_create_user(db, "fresh@example.com", "Fresh")
    syn = users_repo.create_syndicate(db, "Fresh Start", u["id"])
    login(client, db, "fresh@example.com")
    r = client.get(f"/s/{syn['slug']}/stats")
    assert r.status_code == 200
    assert "No graded picks yet." in r.text
    assert "Standings" not in r.text


# --- the parlay -------------------------------------------------------------

def _two_person_week(db, week, owner_side_wins: bool, friend_side_wins: bool, name):
    """A fresh syndicate of two, both picking week `week`, graded."""
    from app.repositories import picks as picks_repo
    from app.repositories import users as users_repo
    from app.services.picks_service import grade_pending
    a = users_repo.get_or_create_user(db, f"{name}-a@example.com", f"{name}A")
    b = users_repo.get_or_create_user(db, f"{name}-b@example.com", f"{name}B")
    syn = users_repo.create_syndicate(db, f"{name} syndicate", a["id"])
    users_repo.add_member(db, syn["id"], b["id"])
    # home wins 27-20, so HOME -3.5 covers and AWAY +3.5 doesn't
    for user, wins in ((a, owner_side_wins), (b, friend_side_wins)):
        picks_repo.upsert_pick(db, syndicate_id=syn["id"], user_id=user["id"],
                               game_id=game_id(week), season=SEASON, week=week,
                               bet_type="SPREAD", line="-3.5" if wins else "3.5",
                               side_team_id=HOME if wins else AWAY)
    db.execute("""UPDATE games SET home_score = 27, away_score = 20, completed = TRUE,
                  status = 'STATUS_FINAL' WHERE id = ?""", [game_id(week)])
    grade_pending(db, syn["id"])
    return syn, a, b


def test_board_calls_out_the_goose(client, db):
    syn, a, b = _two_person_week(db, 2, True, False, "goosey")
    login(client, db, "goosey-a@example.com")
    r = client.get(f"/s/{syn['slug']}", params={"week": 2})
    assert 'data-parlay="MISSED"' in r.text
    assert "gooseyB is the goose" in r.text
    assert r.text.count("data-goose") == 1


def test_board_celebrates_a_hit(client, db):
    syn, a, b = _two_person_week(db, 2, True, True, "hitters")
    login(client, db, "hitters-a@example.com")
    r = client.get(f"/s/{syn['slug']}", params={"week": 2})
    assert 'data-parlay="HIT"' in r.text
    assert "Parlay hit" in r.text
    assert "data-goose" not in r.text


def test_stats_leads_with_parlays_and_geese(client, db):
    syn, a, b = _two_person_week(db, 2, True, False, "statsy")
    login(client, db, "statsy-a@example.com")
    r = client.get(f"/s/{syn['slug']}/stats")
    assert "Parlays hit" in r.text
    assert "Goose count" not in r.text                      # no separate table
    head = r.text[r.text.index('id="standings"'):]
    assert head.index("Win %") < head.index("Geese")        # a column after win %
    row = head[head.index("statsyB"):head.index("</tr>", head.index("statsyB"))]
    assert row.rstrip().endswith('<td class="n text-muted">1</td>')


def test_results_text_goes_out_once_per_season_and_week(db):
    from app.config import get_settings
    from app.services import scheduler
    syn, a, b = _two_person_week(db, 2, True, False, "texty")
    db.execute("UPDATE users SET phone = '5550000000' WHERE id = ?", [a["id"]])
    count = lambda: db.value(
        "SELECT COUNT(*) FROM notifications WHERE syndicate_id = ? AND kind = 'results'", [syn["id"]])
    scheduler._send_results(db, get_settings())
    assert count() == 1
    body = db.value("SELECT body FROM notifications WHERE syndicate_id = ? AND kind = 'results'", [syn["id"]])
    assert body.startswith("Week 2: parlay missed. textyB is the goose.")
    scheduler._send_results(db, get_settings())
    assert count() == 1                                     # not again
    assert db.value("SELECT COUNT(*) FROM results_sent WHERE syndicate_id = ?", [syn["id"]]) == 1
