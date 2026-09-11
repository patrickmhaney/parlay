"""The stats page: the parlay first, then the legs."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from markupsafe import Markup

from app.config import get_settings
from app.db import get_db
from app.deps import render, require_syndicate
from app.formatting import line as fmt_line, signed
from app.repositories import picks as picks_repo
from app.repositories import stats as stats_repo
from app.services.charts import running_chart

router = APIRouter()


def _chart_payload(chart) -> Markup:
    by_x: dict[float, dict] = {}
    for s in chart.series:
        for (x, _y), raw in zip(s.points, s.raw):
            slot = by_x.setdefault(x, {"x": x, "week": raw["week"], "parts": []})
            slot["parts"].append(f"{s.name} {signed(raw['value'])}")
    weeks = [{"x": v["x"], "week": v["week"], "label": "   ".join(v["parts"])}
             for v in sorted(by_x.values(), key=lambda d: d["x"])]
    return Markup(f'<script id="chart-data" type="application/json">{json.dumps({"weeks": weeks})}</script>')


def _pivot(rows: list[dict], key: str, columns: list[str], order: list[str]) -> list[dict]:
    table: dict[str, dict] = {}
    for r in rows:
        table.setdefault(r["display_name"], {})[r[key]] = r
    return [{"name": n, "cells": [table.get(n, {}).get(c) for c in columns]}
            for n in order if n in table]


def _beat_label(b: dict) -> str:
    if b["bet_type"] == "SPREAD":
        return f"{b['side_abbr']} {fmt_line(b['line'])}"
    return f"{'Over' if b['bet_type'] == 'OVER' else 'Under'} {fmt_line(b['line'], signed=False)}"


@router.get("/s/{slug}/stats", name="stats_page")
def stats_page(request: Request, slug: str, season: int | None = None):
    user, syn = require_syndicate(request, slug)
    db = get_db()
    sid = syn["id"]

    seasons = picks_repo.seasons_with_picks(db, sid)
    chart_season = season or (seasons[0] if seasons else get_settings().current_season)
    chart = running_chart(stats_repo.running_record(db, sid, chart_season))

    weeks = stats_repo.parlay_weeks(db, sid, season)
    board = stats_repo.leaderboard(db, sid, season)
    order = [r["display_name"] for r in board]

    beats = stats_repo.bad_beats(db, sid, 8)
    for b in beats:
        b["label"] = _beat_label(b)

    return render(request, "stats.html", {
        "syndicate": syn,
        "active_nav": "stats",
        "season": season,
        "seasons": seasons,
        "chart_season": chart_season,
        "parlays": stats_repo.parlay_summary(weeks),
        "geese": {g["display_name"]: g["count"] for g in stats_repo.goose_counts(db, sid, weeks)},
        "totals": stats_repo.syndicate_totals(db, sid, season),
        "board": board,
        "streaks": sorted(stats_repo.streaks(db, sid),
                          key=lambda r: order.index(r["display_name"]) if r["display_name"] in order else 99),
        "bet_types": _pivot(stats_repo.by_bet_type(db, sid, season), "bet_type",
                            ["SPREAD", "OVER", "UNDER"], order),
        "fav_dog": _pivot(stats_repo.favorite_vs_dog(db, sid, season), "side",
                          ["favorite", "underdog"], order),
        "teams": stats_repo.team_loyalty(db, sid, 10),
        "beats": beats,
        "chart": chart,
        "chart_json": _chart_payload(chart) if not chart.empty else "",
    })
