"""Adapter for ESPN's public NFL scoreboard.

This is the only module that knows ESPN's JSON shape. It is undocumented and
can change without notice, so:

  * every response is cached to disk as raw JSON, which means re-grading and
    backfills never need the network;
  * completed weeks are served from cache forever (a final score is final);
  * parsing is defensive -- a missing odds block or an in-progress game yields
    None rather than an exception.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
SCOREBOARD = BASE + "/scoreboard"
TEAMS = BASE + "/teams"

REGULAR_SEASON = 2
POSTSEASON = 3

# 2021 onward the NFL plays 18 regular-season weeks; 2020 and earlier, 17.
def weeks_in_season(season: int) -> int:
    return 18 if season >= 2021 else 17


@dataclass
class Team:
    id: str
    abbreviation: str
    display_name: str
    short_name: str = ""
    location: str = ""
    color: str = ""
    logo_url: str = ""


@dataclass
class Game:
    id: str
    season: int
    season_type: int
    week: int
    kickoff_at: datetime | None
    home_team_id: str
    away_team_id: str
    home_score: int | None
    away_score: int | None
    status: str
    completed: bool
    favorite_team_id: str | None = None
    spread: Decimal | None = None
    over_under: Decimal | None = None
    odds_provider: str | None = None
    teams: list[Team] = field(default_factory=list)


class EspnClient:
    def __init__(self, cache_dir: Path, timeout: float = 25.0) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    # -- raw fetch + cache ------------------------------------------------

    def _cache_path(self, season: int, season_type: int, week: int) -> Path:
        return self.cache_dir / f"{season}_{season_type}_{week:02d}.json"

    # ESPN's edge rejects browser-like and unrecognised User-Agents with a 403
    # but serves ordinary client-library agents. Leaving httpx's own default in
    # place works; these are fallbacks in case that changes.
    _UA_FALLBACKS = ("curl/7.74.0", "python-requests/2.32.3")

    def _get(self, url: str, params: dict | None = None) -> dict:
        last: Exception | None = None
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as c:
            for attempt, ua in enumerate((None, *self._UA_FALLBACKS)):
                headers = {"User-Agent": ua} if ua else None
                try:
                    r = c.get(url, params=params, headers=headers)
                    r.raise_for_status()
                    return r.json()
                except httpx.HTTPStatusError as exc:
                    last = exc
                    if exc.response.status_code != 403:
                        raise
                    log.warning(
                        "espn 403 on attempt %s (ua=%s); retrying", attempt + 1, ua
                    )
        raise RuntimeError(f"ESPN refused all user agents for {url}") from last

    def scoreboard(
        self,
        season: int,
        week: int,
        season_type: int = REGULAR_SEASON,
        *,
        use_cache: bool = True,
        refresh: bool = False,
    ) -> dict:
        path = self._cache_path(season, season_type, week)
        if use_cache and not refresh and path.exists():
            try:
                cached = json.loads(path.read_text())
                if cached.get("_complete"):
                    return cached
            except (json.JSONDecodeError, OSError):
                log.warning("bad espn cache at %s; refetching", path)

        data = self._get(
            SCOREBOARD, {"dates": season, "seasontype": season_type, "week": week}
        )
        events = data.get("events") or []
        data["_complete"] = bool(events) and all(
            (e.get("competitions") or [{}])[0].get("status", {}).get("type", {}).get("completed")
            for e in events
        )
        data["_fetched_at"] = datetime.now(timezone.utc).isoformat()
        try:
            path.write_text(json.dumps(data))
        except OSError as exc:  # pragma: no cover
            log.warning("could not cache espn response: %s", exc)
        return data

    # -- parsing ----------------------------------------------------------

    def teams(self) -> list[Team]:
        data = self._get(TEAMS)
        out: list[Team] = []
        for sport in data.get("sports", []):
            for league in sport.get("leagues", []):
                for entry in league.get("teams", []):
                    out.append(_parse_team(entry.get("team", {})))
        return out

    def games(
        self,
        season: int,
        week: int,
        season_type: int = REGULAR_SEASON,
        *,
        refresh: bool = False,
    ) -> list[Game]:
        data = self.scoreboard(season, week, season_type, refresh=refresh)
        return parse_games(data, season, week, season_type)


# --- pure parsers (unit-testable against cached fixtures) ------------------


def _parse_team(t: dict) -> Team:
    logo = ""
    logos = t.get("logos") or []
    if logos:
        logo = logos[0].get("href", "")
    elif t.get("logo"):
        logo = t["logo"]
    return Team(
        id=str(t.get("id", "")),
        abbreviation=t.get("abbreviation") or "",
        display_name=t.get("displayName") or "",
        short_name=t.get("shortDisplayName") or "",
        location=t.get("location") or "",
        color=t.get("color") or "",
        logo_url=logo,
    )


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(
            timezone.utc
        ).replace(tzinfo=None)
    except ValueError:
        return None


_SPREAD_RE = re.compile(r"^([A-Z]{2,4})\s+(-?\+?[\d.]+)$")


def _parse_odds(comp: dict, abbr_to_id: dict[str, str]) -> tuple:
    """Returns (favorite_team_id, spread, over_under, provider)."""
    odds_list = comp.get("odds") or []
    if not odds_list:
        return None, None, None, None
    o = odds_list[0]
    provider = (o.get("provider") or {}).get("name")

    ou = o.get("overUnder")
    over_under = Decimal(str(ou)) if ou is not None else None

    fav_id, spread = None, None
    details = (o.get("details") or "").strip()
    m = _SPREAD_RE.match(details)
    if m:
        abbr, num = m.group(1), m.group(2).lstrip("+")
        fav_id = abbr_to_id.get(abbr)
        try:
            spread = Decimal(num)
        except Exception:
            spread = None
    elif details.upper() in {"EVEN", "PK", "PICK"}:
        spread = Decimal("0")
    return fav_id, spread, over_under, provider


def parse_games(data: dict, season: int, week: int, season_type: int) -> list[Game]:
    games: list[Game] = []
    for event in data.get("events") or []:
        comps = event.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]

        home = away = None
        teams: list[Team] = []
        for c in comp.get("competitors") or []:
            team = _parse_team(c.get("team") or {})
            teams.append(team)
            score = c.get("score")
            try:
                score = int(score) if score not in (None, "") else None
            except (TypeError, ValueError):
                score = None
            if c.get("homeAway") == "home":
                home = (team, score)
            else:
                away = (team, score)
        if not home or not away:
            continue

        abbr_to_id = {t.abbreviation: t.id for t in teams}
        fav_id, spread, over_under, provider = _parse_odds(comp, abbr_to_id)

        status_block = (comp.get("status") or {}).get("type") or {}
        status = status_block.get("name") or "STATUS_SCHEDULED"
        completed = bool(status_block.get("completed"))

        games.append(
            Game(
                id=str(event.get("id")),
                season=season,
                season_type=season_type,
                week=week,
                kickoff_at=_parse_dt(event.get("date")),
                home_team_id=home[0].id,
                away_team_id=away[0].id,
                home_score=home[1] if completed else home[1],
                away_score=away[1] if completed else away[1],
                status=status,
                completed=completed,
                favorite_team_id=fav_id,
                spread=spread,
                over_under=over_under,
                odds_provider=provider,
                teams=teams,
            )
        )
    return games
