"""Application configuration, sourced entirely from the environment.

Nothing secret is ever hardcoded here. See .env.example for the full list.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- core ---
    app_name: str = "Parlay Syndicate"
    base_url: str = "http://localhost:8080"
    secret_key: str = "dev-only-insecure-key-change-me"
    debug: bool = False

    # --- storage ---
    database_path: Path = BASE_DIR / "data" / "parlay.duckdb"
    espn_cache_dir: Path = BASE_DIR / "data" / "espn_cache"

    # --- sessions ---
    session_days: int = 120
    session_cookie: str = "parlay_session"
    login_token_minutes: int = 15
    invite_token_days: int = 14

    # --- email (magic links + invites) ---
    # provider: "console" writes the link to the log + a local file, which is
    # what runs until a real sender is configured.
    email_provider: str = "console"
    email_from: str = "Parlay Syndicate <noreply@parlaysyndicate.com>"
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # --- sms ---
    sms_enabled: bool = False
    textbelt_key: str = ""
    textbelt_url: str = "https://textbelt.com/text"

    # --- scheduler ---
    scheduler_enabled: bool = True
    # Nightly-ish grading sweep; NFL weeks close out Monday night.
    grade_cron_hour: int = 11  # 11:00 UTC ~ 6am Eastern
    grade_cron_minute: int = 0
    sync_cron_hour: int = 12
    sync_cron_minute: int = 30

    # --- season ---
    current_season: int = 2026
    timezone: str = "America/New_York"

    @property
    def session_cookie_secure(self) -> bool:
        return self.base_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.database_path.parent.mkdir(parents=True, exist_ok=True)
    s.espn_cache_dir.mkdir(parents=True, exist_ok=True)
    return s
