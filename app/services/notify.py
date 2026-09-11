"""Outbound email and SMS.

The old app wrote form input to a CSV, turned that into a bash config, and had
send_text.sh run `. picks.cfg` -- which executed anything a player typed into
the line field. Everything here goes over HTTP from Python; nothing is ever
handed to a shell.
"""
from __future__ import annotations

import logging
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import httpx

from app.config import get_settings
from app.db import Database

log = logging.getLogger(__name__)


def _record(db: Database, kind: str, channel: str, recipient: str, body: str,
            status: str, error: str | None = None, syndicate_id: str | None = None) -> None:
    try:
        db.execute(
            """INSERT INTO notifications (id, syndicate_id, kind, channel, recipient,
                                          body, status, error, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [uuid.uuid4().hex, syndicate_id, kind, channel, recipient, body,
             status, error, datetime.now(timezone.utc).replace(tzinfo=None)],
        )
    except Exception:  # logging must never break the request
        log.exception("could not record notification")


# --- email -----------------------------------------------------------------


def send_email(db: Database, to: str, subject: str, body: str, kind: str = "login") -> bool:
    settings = get_settings()
    provider = settings.email_provider.lower()

    if provider == "console":
        outbox = Path(settings.database_path).parent / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        path = outbox / f"{stamp}_{kind}_{to.replace('@', '_at_')}.txt"
        path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n")
        log.info("EMAIL (console) -> %s | %s | saved to %s", to, subject, path)
        print(f"\n--- EMAIL to {to} ---\n{subject}\n\n{body}\n--- end ---\n", flush=True)
        _record(db, kind, "email", to, body, "sent")
        return True

    try:
        if provider == "resend":
            if not settings.resend_api_key:
                raise RuntimeError("RESEND_API_KEY is not set")
            r = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={"from": settings.email_from, "to": [to],
                      "subject": subject, "text": body},
                timeout=20.0,
            )
            if r.status_code >= 400:
                try:
                    reason = r.json().get("message") or r.text
                except Exception:
                    reason = r.text
                raise RuntimeError(f"Resend {r.status_code}: {reason}")
        elif provider == "smtp":
            if not settings.smtp_host:
                raise RuntimeError("SMTP_HOST is not set")
            msg = EmailMessage()
            msg["From"] = settings.email_from
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
                s.starttls()
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        else:
            raise RuntimeError(f"unknown EMAIL_PROVIDER {provider!r}")
    except Exception as exc:
        log.error("email to %s failed: %s", to, exc)
        _record(db, kind, "email", to, body, "failed", str(exc))
        return False

    _record(db, kind, "email", to, body, "sent")
    return True


# --- sms -------------------------------------------------------------------


def send_sms(db: Database, phone: str, message: str, kind: str = "picks_in",
             syndicate_id: str | None = None) -> bool:
    settings = get_settings()
    if not settings.sms_enabled or not settings.textbelt_key:
        log.info("SMS disabled; would have texted %s: %s", phone, message)
        _record(db, kind, "sms", phone, message, "skipped",
                "SMS_ENABLED is false or TEXTBELT_KEY is unset", syndicate_id)
        return False
    try:
        r = httpx.post(
            settings.textbelt_url,
            data={"phone": phone, "message": message, "key": settings.textbelt_key},
            timeout=20.0,
        )
        r.raise_for_status()
        payload = r.json()
        if not payload.get("success"):
            raise RuntimeError(payload.get("error", "textbelt rejected the message"))
    except Exception as exc:
        log.error("sms to %s failed: %s", phone, exc)
        _record(db, kind, "sms", phone, message, "failed", str(exc), syndicate_id)
        return False
    _record(db, kind, "sms", phone, message, "sent", None, syndicate_id)
    return True


# --- composed messages -----------------------------------------------------


def picks_are_in_message(picks: list[dict], base_url: str) -> str:
    """Deliberately the same shape as the original text -- that part worked."""
    lines = ["The picks are in!"]
    for p in picks:
        lines.append(f"-{p['display_name']}: {p['summary']}")
    lines.append(base_url)
    return "\n".join(lines)


def results_message(week: int, rows: list[dict], base_url: str) -> str:
    lines = [f"Week {week} results:"]
    for r in rows:
        mark = {"WIN": "W", "LOSS": "L", "PUSH": "P"}.get(r["outcome"], "?")
        lines.append(f"-{r['display_name']}: {mark}  {r['summary']}")
    lines.append(base_url)
    return "\n".join(lines)
