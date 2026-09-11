"""Server-rendered chart geometry.

DuckDB aggregates, Python computes coordinates, Jinja draws SVG. No chart
library and no CDN, so the dashboard works on a phone with bad signal.

Only geometry lives here -- colours come from CSS custom properties so the
charts follow the light/dark theme like everything else.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Series:
    name: str
    slot: int                      # 1..5 -> var(--series-N)
    points: list[tuple[float, float]] = field(default_factory=list)  # (x, y) px
    polyline: str = ""
    end_x: float = 0.0
    end_y: float = 0.0
    end_value: float = 0.0
    raw: list[dict] = field(default_factory=list)


@dataclass
class LineChart:
    width: int
    height: int
    pad_l: int
    pad_r: int
    pad_t: int
    pad_b: int
    series: list[Series]
    x_ticks: list[dict]
    y_ticks: list[dict]
    zero_y: float | None
    x_label: str = ""
    y_label: str = ""
    empty: bool = True


def _nice_bounds(lo: float, hi: float) -> tuple[float, float, float]:
    """Round outward to a readable step."""
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    span = hi - lo
    raw_step = span / 4
    magnitude = 10 ** (len(str(int(abs(raw_step)))) - 1) if abs(raw_step) >= 1 else 0.5
    for mult in (1, 2, 2.5, 5, 10):
        step = magnitude * mult
        if step >= raw_step:
            break
    lo_r = step * (int(lo / step) - (1 if lo % step else 0)) if lo < 0 else step * int(lo / step)
    hi_r = step * (int(hi / step) + (1 if hi % step else 0))
    if hi_r <= lo_r:
        hi_r = lo_r + step
    return lo_r, hi_r, step


def running_chart(
    series_data: dict[str, list[dict]],
    *,
    width: int = 760,
    height: int = 320,
) -> LineChart:
    """A running per-player value (wins minus losses), week by week."""
    pad_l, pad_r, pad_t, pad_b = 44, 72, 16, 34
    chart = LineChart(
        width=width, height=height, pad_l=pad_l, pad_r=pad_r, pad_t=pad_t,
        pad_b=pad_b, series=[], x_ticks=[], y_ticks=[], zero_y=None,
        x_label="Week", y_label="Wins minus losses",
    )
    if not series_data:
        return chart

    all_weeks = sorted({p["week"] for pts in series_data.values() for p in pts})
    all_units = [p["value"] for pts in series_data.values() for p in pts]
    if not all_weeks or not all_units:
        return chart
    chart.empty = False

    x_min, x_max = min(all_weeks), max(all_weeks)
    y_lo, y_hi, y_step = _nice_bounds(min(all_units + [0]), max(all_units + [0]))

    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def sx(week: float) -> float:
        if x_max == x_min:
            return pad_l + plot_w / 2
        return pad_l + (week - x_min) / (x_max - x_min) * plot_w

    def sy(units: float) -> float:
        return pad_t + (y_hi - units) / (y_hi - y_lo) * plot_h

    # y grid
    n = 0
    v = y_lo
    while v <= y_hi + 1e-9 and n < 12:
        chart.y_ticks.append({
            "value": round(v, 2),
            "label": "0" if abs(v) < 1e-9 else (f"{v:+.0f}" if abs(v) >= 1 else f"{v:+.1f}"),
            "y": round(sy(v), 2),
        })
        v += y_step
        n += 1
    chart.zero_y = round(sy(0), 2) if y_lo <= 0 <= y_hi else None

    # x ticks -- every week if few, else every other
    stride = 1 if len(all_weeks) <= 10 else 2
    for i, w in enumerate(all_weeks):
        if i % stride == 0 or w == all_weeks[-1]:
            chart.x_ticks.append({"label": str(w), "x": round(sx(w), 2)})

    for slot, name in enumerate(sorted(series_data), start=1):
        pts = series_data[name]
        coords = [(round(sx(p["week"]), 2), round(sy(p["value"]), 2)) for p in pts]
        s = Series(
            name=name,
            slot=((slot - 1) % 5) + 1,
            points=coords,
            polyline=" ".join(f"{x},{y}" for x, y in coords),
            raw=pts,
        )
        if coords:
            s.end_x, s.end_y = coords[-1]
            s.end_value = pts[-1]["value"]
        chart.series.append(s)

    # Nudge overlapping end labels apart so direct labelling stays readable.
    ordered = sorted(chart.series, key=lambda s: s.end_y)
    for i in range(1, len(ordered)):
        gap = ordered[i].end_y - ordered[i - 1].end_y
        if gap < 13:
            ordered[i].end_y = ordered[i - 1].end_y + 13
    return chart


@dataclass
class BarRow:
    label: str
    value: float
    display: str
    pct: float          # 0..100 width of the bar
    negative: bool


def bar_rows(rows: list[dict], label_key: str, value_key: str,
             fmt: str = "{:+.2f}") -> list[BarRow]:
    """Horizontal bars sharing one scale, signed around zero."""
    vals = [float(r[value_key] or 0) for r in rows]
    if not vals:
        return []
    peak = max(abs(v) for v in vals) or 1.0
    out = []
    for r in rows:
        v = float(r[value_key] or 0)
        out.append(BarRow(
            label=r[label_key],
            value=v,
            display=fmt.format(v),
            pct=round(abs(v) / peak * 100, 2),
            negative=v < 0,
        ))
    return out
