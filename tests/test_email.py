"""Email delivery. Resend itself can't be called from tests, so these pin the
exact request we send and how the site behaves when Resend refuses it."""
from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.services import notify


class FakeResponse:
    def __init__(self, status: int, body: dict | None = None):
        self.status_code = status
        self._body = body or {}
        self.request = httpx.Request("POST", "https://api.resend.com/emails")
        self.text = str(self._body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


@pytest.fixture()
def resend(monkeypatch):
    """Switch the app to Resend and capture outgoing requests."""
    s = get_settings()
    monkeypatch.setattr(s, "email_provider", "resend")
    monkeypatch.setattr(s, "resend_api_key", "re_test_key")
    calls: list[dict] = []
    reply = {"status": 200}

    def fake_post(url, **kw):
        calls.append({"url": url, **kw})
        if reply["status"] >= 400:
            return FakeResponse(reply["status"], {"message": "The domain is not verified"})
        return FakeResponse(reply["status"], {"id": "msg_123"})

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    return {"calls": calls, "reply": reply}


def test_resend_request_shape(db, resend):
    ok = notify.send_email(db, "friend@example.com", "Sign in to Parlay", "body text")
    assert ok
    (call,) = resend["calls"]
    assert call["url"] == "https://api.resend.com/emails"
    assert call["headers"]["Authorization"] == "Bearer re_test_key"
    assert call["json"]["to"] == ["friend@example.com"]
    assert call["json"]["subject"] == "Sign in to Parlay"
    assert call["json"]["text"] == "body text"
    assert "parlaysyndicate.com" in call["json"]["from"]


def test_resend_refusal_is_reported_not_swallowed(db, resend):
    resend["reply"]["status"] = 403   # e.g. domain not verified yet
    assert notify.send_email(db, "friend@example.com", "s", "b") is False


def test_login_page_says_so_when_email_fails(client, resend):
    resend["reply"]["status"] = 403
    r = client.post("/login", data={"email": "fails@example.com"})
    assert r.status_code == 502
    assert "send the email. Try again" in r.text
    assert "Check your email" not in r.text


def test_login_email_contains_a_working_link(client, resend):
    r = client.post("/login", data={"email": "works@example.com"})
    assert r.status_code == 200
    body = resend["calls"][-1]["json"]["text"]
    assert "http://testserver/auth/verify?token=" in body


def test_login_links_are_rate_limited_per_address(client, db, resend):
    email = "flooded@example.com"
    for _ in range(6):
        r = client.post("/login", data={"email": email})
        assert r.status_code == 200          # same page every time
    sent_to = [c["json"]["to"][0] for c in resend["calls"]]
    assert sent_to.count(email) == 3


def test_failed_sends_do_not_count_toward_the_rate_limit(client, db, resend):
    email = "unlucky@example.com"
    resend["reply"]["status"] = 403
    for _ in range(4):
        assert client.post("/login", data={"email": email}).status_code == 502
    resend["reply"]["status"] = 200
    r = client.post("/login", data={"email": email})
    assert r.status_code == 200
    assert resend["calls"][-1]["json"]["to"] == [email]   # actually sent


def test_provider_reason_is_logged(db, resend, caplog):
    resend["reply"]["status"] = 403
    notify.send_email(db, "x@example.com", "s", "b")
    assert "not verified" in caplog.text
