"""Magic-link sign-in, sign-out and invite acceptance."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.db import get_db
from app.deps import redirect, render, require_user
from app.repositories import users as users_repo
from app.services import auth, notify

log = logging.getLogger(__name__)
router = APIRouter()

LOGIN_LINKS_PER_WINDOW = 3  # per address, per 15 minutes


def _home_for(db, user: dict) -> str:
    syns = users_repo.syndicates_for_user(db, user["id"])
    return f"/s/{syns[0]['slug']}" if syns else "/start"


@router.get("/")
def index(request: Request):
    user = auth.current_user(request)
    if user:
        return redirect(_home_for(get_db(), user))
    return render(request, "login.html", {"next_url": None, "new": False, "error": None})


@router.get("/login")
def login_form(request: Request, next: str | None = None, new: int = 0):
    if auth.current_user(request):
        return redirect(_home_for(get_db(), auth.current_user(request)))
    return render(request, "login.html", {"next_url": next, "new": bool(new), "error": None})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    next: str | None = Form(None),
    new: int = Form(0),
    syndicate_name: str = Form(""),
):
    email = (email or "").strip().lower()
    if "@" not in email or len(email) < 5:
        return render(request, "login.html",
                      {"error": "Enter a valid email address.",
                       "next_url": next, "new": bool(new)})

    db = get_db()
    settings = get_settings()

    # Cap how often the site will email one address, so it can't be used to
    # flood someone's inbox (or burn the sending quota). Past the cap we show
    # the same confirmation page, so the limit reveals nothing about accounts.
    if auth.recent_login_requests(db, email) >= LOGIN_LINKS_PER_WINDOW:
        log.warning("login link rate limit hit for %s", email)
        return render(request, "login_sent.html", {"email": email, "dev_link": None})

    # Remember the intent to create a syndicate until the link is clicked.
    redirect_to = next
    if new and syndicate_name.strip():
        redirect_to = "/new-syndicate?" + urlencode({"name": syndicate_name.strip()[:60]})

    link = auth.issue_login_link(db, email, redirect_to)
    sent = notify.send_email(
        db, email, "Sign in to Parlay",
        f"Sign in to Parlay:\n\n{link}\n\n"
        "This link works once and expires in 15 minutes. "
        "If you didn't request it, you can ignore this email.",
        kind="login",
    )
    if not sent:
        auth.revoke_login_link(db, link)
        return render(request, "login.html", {
            "error": "We couldn't send the email. Try again in a minute.",
            "next_url": next, "new": bool(new),
        }, status_code=502)

    # Showing the link on screen is only acceptable in local development.
    # On a public site it would hand anyone a login to any account.
    dev_link = link if (settings.debug and settings.email_provider.lower() == "console") else None
    return render(request, "login_sent.html", {"email": email, "dev_link": dev_link})


@router.get("/auth/verify")
def verify(request: Request, token: str = ""):
    db = get_db()
    result = auth.redeem_login_token(db, token)
    if not result:
        return render(request, "message.html", {
            "heading": "Link expired",
            "body": "Sign-in links work once, for 15 minutes.",
            "link": "/login", "link_text": "Get a new link",
        }, status_code=400)

    user, session_token, redirect_to = result
    # Only ever follow a same-site path, never an absolute URL from a link.
    target = redirect_to if (redirect_to or "").startswith("/") else _home_for(db, user)
    response = RedirectResponse(target, status_code=303)
    auth.set_session_cookie(response, session_token)
    return response


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(get_settings().session_cookie)
    if token:
        auth.logout(get_db(), token)
    response = redirect("/")
    auth.clear_session_cookie(response)
    return response


@router.get("/start")
def start_page(request: Request):
    """Signed in, but not in any syndicate yet: create one (or sign out and
    use the address you were invited with)."""
    user = require_user(request)
    if users_repo.syndicates_for_user(get_db(), user["id"]):
        return redirect(_home_for(get_db(), user))
    return render(request, "start.html")


@router.post("/start")
def start_submit(request: Request, name: str = Form(...)):
    user = require_user(request)
    syn = users_repo.create_syndicate(get_db(), name.strip()[:60] or f"{user['display_name']}'s syndicate", user["id"])
    return redirect(f"/s/{syn['slug']}/settings")


@router.get("/new-syndicate")
def new_syndicate(request: Request, name: str = ""):
    user = require_user(request)
    db = get_db()
    name = (name or "").strip()[:60] or f"{user['display_name']}'s Syndicate"
    syn = users_repo.create_syndicate(db, name, user["id"])
    return redirect(f"/s/{syn['slug']}/settings")


@router.get("/invite/{token}")
def invite_landing(request: Request, token: str):
    db = get_db()
    inv = auth.lookup_invite(db, token)
    if not inv:
        return render(request, "message.html", {
            "heading": "Invite expired",
            "body": "Ask for a new one.",
        }, status_code=400)

    user = auth.current_user(request)
    if not user:
        # Send them through sign-in, then straight back to this invite.
        return redirect(f"/login?next=/invite/{token}")

    syn = users_repo.get_syndicate(db, inv["syndicate_id"])
    return render(request, "invite.html", {"inv_syndicate": syn, "token": token})


@router.post("/invite/{token}")
def invite_accept(request: Request, token: str):
    user = require_user(request)
    db = get_db()
    inv = auth.lookup_invite(db, token)
    if not inv:
        return render(request, "message.html", {
            "heading": "Invite expired",
            "body": "Ask for a new one.",
        }, status_code=400)
    users_repo.add_member(db, inv["syndicate_id"], user["id"])
    users_repo.accept_invite(db, auth.hash_token(token), user["id"])
    syn = users_repo.get_syndicate(db, inv["syndicate_id"])
    return redirect(f"/s/{syn['slug']}")
