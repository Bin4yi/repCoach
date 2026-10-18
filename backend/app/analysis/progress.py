"""Compare sessions over time. Pure functions over stored session documents."""
from __future__ import annotations

import numpy as np

MIN_SESSIONS_FOR_TREND = 3
TREND_CHANGE_POINTS = 5.0   # form score must move this much (fitted line, first->last) to count as a trend


def point(doc: dict) -> dict:
    """The few numbers we track per session."""
    j = doc.get("judgement") or {}
    s = doc.get("set") or {}
    return {
        "date": doc.get("created_at"),
        "exercise": doc.get("exercise"),
        "form_score": j.get("form_score"),
        "depth": s.get("depth_mean"),
        "relative_load": j.get("relative_load"),
        "load_kg": (doc.get("inputs") or {}).get("load_kg"),
        "rep_count": s.get("rep_count"),
    }


def _mean(vals: list[float | None]) -> float | None:
    v = [x for x in vals if x is not None]
    return float(np.mean(v)) if v else None


def compare_with_last_n(current: dict, history: list[dict], n: int = 3) -> dict | None:
    """Change vs the average of the last `n` earlier sessions of the SAME exercise.

    `current` and `history` items are `point()` dicts; history is newest first. Returns None with no history.
    """
    prev = [p for p in history if p["exercise"] == current["exercise"]][:n]
    if not prev:
        return None
    out = {"sessions_compared": len(prev)}
    for key, name, nd in (("form_score", "form_score_change", 0), ("depth", "depth_change_deg", 1),
                          ("relative_load", "relative_load_change", 2)):
        base, cur = _mean([p[key] for p in prev]), current.get(key)
        out[name] = round(cur - base, nd) if base is not None and cur is not None else None
        if nd == 0 and out[name] is not None:
            out[name] = int(out[name])
    return out


def trend(points: list[dict]) -> str:
    """improving | stable | declining | not_enough_data from form scores (oldest -> newest)."""
    scores = [p["form_score"] for p in points if p.get("form_score") is not None]
    if len(scores) < MIN_SESSIONS_FOR_TREND:
        return "not_enough_data"
    x = np.arange(len(scores))
    slope = float(np.polyfit(x, scores, 1)[0])
    change = slope * (len(scores) - 1)
    if change >= TREND_CHANGE_POINTS:
        return "improving"
    if change <= -TREND_CHANGE_POINTS:
        return "declining"
    return "stable"


def history_summary(points_newest_first: list[dict], n: int = 6) -> dict:
    """Compact numbers handed to the progress-summary prompt."""
    pts = list(reversed(points_newest_first[:n]))
    return {
        "sessions": len(pts),
        "trend": trend(pts),
        "form_scores": [p["form_score"] for p in pts],
        "depth_values": [p["depth"] for p in pts],
        "relative_loads": [p["relative_load"] for p in pts],
        "exercises": sorted({p["exercise"] for p in pts}),
    }
