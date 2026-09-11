"""Display formatting shared by every template.

Numbers use a true minus sign (U+2212) for display only; form inputs and text
messages keep ASCII so they can be typed and parsed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.config import get_settings

MINUS = "−"


def _dec(v) -> Decimal | None:
    if v is None or v == "":
        return None
    d = v if isinstance(v, Decimal) else Decimal(str(v))
    d = d.normalize()
    if d == d.to_integral_value():
        d = d.quantize(Decimal(1))
    return d


def line(v, signed: bool = True) -> str:
    """-3.5 -> '−3.5', 3 -> '+3', 44.5 (signed=False) -> '44.5'."""
    d = _dec(v)
    if d is None:
        return ""
    if d == 0:
        return "PK" if signed else "0"
    text = format(abs(d), "f")
    if not signed:
        return format(d, "f")
    return f"{MINUS}{text}" if d < 0 else f"+{text}"


def signed(n) -> str:
    """3 -> '+3', -2 -> '−2', 0 -> '0'."""
    n = int(n or 0)
    return f"+{n}" if n > 0 else (f"{MINUS}{-n}" if n < 0 else "0")


def record(w, l, p=0) -> str:
    base = f"{w or 0}–{l or 0}"
    return f"{base}–{p}" if p else base


def local(dt: datetime | None) -> datetime | None:
    """Stored timestamps are naive UTC; show them in the syndicate's zone."""
    if dt is None:
        return None
    tz = ZoneInfo(get_settings().timezone)
    return dt.replace(tzinfo=timezone.utc).astimezone(tz)


def kick(dt: datetime | None) -> str:
    """'Thu 8:15 PM'"""
    d = local(dt)
    return d.strftime("%a %-I:%M %p") if d else ""


def day(dt: datetime | None) -> str:
    """'Thu'"""
    d = local(dt)
    return d.strftime("%a") if d else ""


def daterange(start: datetime | None, end: datetime | None) -> str:
    """'Sep 10 – 14', or 'Sep 28 – Oct 2' across a month boundary."""
    a, b = local(start), local(end)
    if not a or not b:
        return ""
    if a.date() == b.date():
        return a.strftime("%b %-d")
    if a.month == b.month:
        return f"{a.strftime('%b %-d')} – {b.day}"
    return f"{a.strftime('%b %-d')} – {b.strftime('%b %-d')}"


def install(env) -> None:
    env.filters.update(line=line, signed=signed, kick=kick, day=day)
    env.globals.update(record=record, daterange=daterange)
