"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, get_settings
from app.db import close_db, get_db
from app.deps import LoginRequired, render
from app.routers import auth_routes, board_routes, settings_routes, stats_routes
from app.services import scheduler

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    db = get_db()
    applied = db.migrate()
    if applied:
        log.info("applied migrations: %s", applied)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()
        close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan, docs_url=None, redoc_url=None)

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

    app.include_router(auth_routes.router)
    app.include_router(board_routes.router)
    app.include_router(stats_routes.router)
    app.include_router(settings_routes.router)

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, exc: LoginRequired):
        return RedirectResponse(f"/login?next={exc.next_url}", status_code=303)

    @app.get("/health", include_in_schema=False)
    def health():
        try:
            n = get_db().value("SELECT COUNT(*) FROM picks")
            return {"status": "ok", "picks": n}
        except Exception as exc:
            return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)

    @app.exception_handler(404)
    async def _not_found(request: Request, exc):
        return render(request, "message.html", {
            "heading": "Not found",
            "body": None,
            "link": "/", "link_text": "Home",
        }, status_code=404)

    return app


app = create_app()
