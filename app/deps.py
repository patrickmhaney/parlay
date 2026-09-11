"""Shared request plumbing: templates, auth guards and syndicate scoping."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import formatting
from app.config import get_settings
from app.db import get_db
from app.repositories import users as users_repo
from app.services import auth

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
formatting.install(templates.env)


def _asset_version() -> str:
    """Short hash of the built CSS. Appended to static URLs so a deploy
    busts Cloudflare's and browsers' caches instead of serving new HTML with
    an hour-old stylesheet."""
    import hashlib
    css = Path(__file__).resolve().parent / "static" / "css" / "app.css"
    try:
        return hashlib.sha1(css.read_bytes()).hexdigest()[:10]
    except OSError:
        return "dev"


templates.env.globals["asset_v"] = _asset_version()


class LoginRequired(Exception):
    def __init__(self, next_url: str) -> None:
        self.next_url = next_url


def render(request: Request, name: str, ctx: dict | None = None, **kw):
    settings = get_settings()
    base = {
        "request": request,
        "app_name": settings.app_name,
        "user": auth.current_user(request),
        "syndicate": None,
        "member_count": 0,
        "active_nav": None,
        "flash": None,
        "current_season": settings.current_season,
    }
    base.update(ctx or {})
    return templates.TemplateResponse(name, base, **kw)


def require_user(request: Request) -> dict:
    user = auth.current_user(request)
    if not user:
        raise LoginRequired(str(request.url.path))
    return user


def require_syndicate(request: Request, slug: str) -> tuple[dict, dict]:
    """Returns (user, syndicate); 404s rather than 403s for non-members so a
    syndicate's existence isn't leaked."""
    user = require_user(request)
    db = get_db()
    syn = users_repo.get_syndicate_by_slug(db, slug)
    if not syn or not users_repo.is_member(db, syn["id"], user["id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such syndicate")
    return user, syn


def redirect(url: str, status_code: int = status.HTTP_303_SEE_OTHER) -> RedirectResponse:
    return RedirectResponse(url, status_code=status_code)
