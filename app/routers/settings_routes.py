"""Members, invites and syndicate configuration."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request

from app.config import get_settings
from app.db import get_db
from app.deps import redirect, render, require_syndicate
from app.repositories import users as users_repo
from app.services import auth, notify

router = APIRouter()


def _settings_context(request: Request, syn: dict, user: dict, **extra) -> dict:
    db = get_db()
    role = users_repo.role_of(db, syn["id"], user["id"])
    ctx = {
        "syndicate": syn,
        "active_nav": "settings",
        "members": users_repo.members(db, syn["id"]),
        "invites": users_repo.pending_invites(db, syn["id"]),
        "is_owner": role == "owner",
        "member_count": users_repo.member_count(db, syn["id"]),
        "sms_disabled": not get_settings().sms_enabled,
        "invite_link": None,
        "error": None,
        "saved_section": None,
    }
    ctx.update(extra)
    return ctx


@router.get("/s/{slug}/settings", name="settings_page")
def settings_page(request: Request, slug: str, saved: str = ""):
    user, syn = require_syndicate(request, slug)
    return render(request, "settings.html",
                  _settings_context(request, syn, user, saved_section=saved or None))


@router.post("/s/{slug}/invite", name="invite_route")
def invite_route(request: Request, slug: str, email: str = Form(...)):
    user, syn = require_syndicate(request, slug)
    db = get_db()
    if users_repo.role_of(db, syn["id"], user["id"]) != "owner":
        return render(request, "settings.html",
                      _settings_context(request, syn, user,
                                        error="Only the owner can invite."),
                      status_code=403)

    email = email.strip().lower()
    link = auth.issue_invite_link(db, syn["id"], email, user["id"])
    notify.send_email(
        db, email, f"{user['display_name']} invited you to {syn['name']}",
        f"{user['display_name']} invited you to join {syn['name']} on Parlay:\n\n"
        f"{link}\n\nThe invite expires in 14 days.",
        kind="invite",
    )
    return render(request, "settings.html",
                  _settings_context(request, syn, user, invite_link=link))


@router.post("/s/{slug}/members", name="update_member_route")
def update_member_route(
    request: Request, slug: str, user_id: str = Form(...),
    email: str = Form(""), phone: str = Form(""),
):
    user, syn = require_syndicate(request, slug)
    db = get_db()
    if users_repo.role_of(db, syn["id"], user["id"]) != "owner":
        return render(request, "settings.html",
                      _settings_context(request, syn, user,
                                        error="Only the owner can edit members."),
                      status_code=403)
    if not users_repo.is_member(db, syn["id"], user_id):
        return redirect(f"/s/{slug}/settings")

    fields = {}
    email = email.strip().lower()
    if email:
        clash = users_repo.get_user_by_email(db, email)
        if clash and clash["id"] != user_id:
            return render(request, "settings.html",
                          _settings_context(request, syn, user,
                                            error=f"{email} is already in use."),
                          status_code=400)
        fields["email"] = email
    fields["phone"] = phone.strip() or None
    users_repo.update_user(db, user_id, **fields)
    return redirect(f"/s/{slug}/settings?saved=members")


@router.post("/s/{slug}/me", name="update_me_route")
def update_me_route(
    request: Request, slug: str, display_name: str = Form(""), phone: str = Form(""),
):
    user, syn = require_syndicate(request, slug)
    users_repo.update_user(
        get_db(), user["id"],
        display_name=display_name.strip() or user["display_name"],
        phone=phone.strip() or None,
    )
    return redirect(f"/s/{slug}/settings?saved=account")


@router.post("/s/{slug}/syndicate", name="update_syndicate_route")
def update_syndicate_route(
    request: Request, slug: str, name: str = Form(""),
    juice_odds: int = Form(-110), lock_at_kickoff: str = Form(""),
):
    user, syn = require_syndicate(request, slug)
    db = get_db()
    if users_repo.role_of(db, syn["id"], user["id"]) != "owner":
        return render(request, "settings.html",
                      _settings_context(request, syn, user,
                                        error="Only the owner can change this."),
                      status_code=403)
    if juice_odds == 0 or -100 < juice_odds < 100:
        return render(request, "settings.html",
                      _settings_context(request, syn, user,
                                        error="Enter juice as American odds, like -110."),
                      status_code=400)
    users_repo.update_syndicate(
        db, syn["id"], name=name.strip() or syn["name"],
        juice_odds=juice_odds, lock_at_kickoff=bool(lock_at_kickoff),
    )
    syn = users_repo.get_syndicate(db, syn["id"])
    return redirect(f"/s/{syn['slug']}/settings?saved=syndicate")
