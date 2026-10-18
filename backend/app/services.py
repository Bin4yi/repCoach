"""Shared read-side helpers: derived values, session summaries, chart series, dashboard warnings."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .analysis import progress
from .analysis.activity import DEFAULT_TZ, as_utc, local_date

NO_UPLOAD_DAYS = 10
READY = ("ready_for_review", "approved")


def bmi(profile: dict) -> dict | None:
    """BMI is shown to the coach only, with a caveat. Computed in code."""
    h, w = profile.get("height_cm"), profile.get("body_weight_kg")
    if not h or not w:
        return None
    return {"value": round(w / ((h / 100) ** 2), 1),
            "note": "BMI is a rough number. It ignores muscle, build and age. Do not use it alone."}


def client_safe_profile(client: dict) -> dict:
    """Profile fields a client may see (never coach notes)."""
    p = dict(client.get("profile") or {})
    p.pop("coach_notes", None)
    return p


def session_row(s: dict) -> dict:
    """Compact session summary for lists."""
    m = s.get("set") or {}
    j = s.get("judgement") or {}
    return {
        "id": s["_id"], "exercise": s["exercise"], "status": s["status"], "created_at": s["created_at"],
        "form_score": m.get("form_score"), "rep_count": m.get("rep_count"),
        "flags": [f["code"] for f in (s.get("flags") or [])],
        "pain": bool((j.get("safety") or {}).get("pain_reported") or (s.get("inputs") or {}).get("pain_during_set")),
        "load_kg": (s.get("inputs") or {}).get("load_kg"),
        "reshoot_reason": (s.get("quality") or {}).get("reason") if s["status"] == "needs_reshoot" else None,
    }


def build_series(sessions_oldest_first: list[dict]) -> dict[str, list[dict]]:
    """Chart data per exercise: form score, depth, tempo and relative strength over time."""
    out: dict[str, list[dict]] = {}
    for s in sessions_oldest_first:
        if s["status"] not in READY or not s.get("set"):
            continue
        m, j = s["set"], s.get("judgement") or {}
        out.setdefault(s["exercise"], []).append({
            "session_id": s["_id"], "date": s["created_at"], "form_score": m.get("form_score"),
            "depth": m.get("depth_mean"), "eccentric_s": m.get("avg_eccentric_s"),
            "concentric_s": m.get("avg_concentric_s"), "relative_load": j.get("relative_load"),
            "load_kg": (s.get("inputs") or {}).get("load_kg"), "rep_count": m.get("rep_count"),
        })
    return out


def latest_trend(sessions_newest_first: list[dict]) -> str:
    pts = [progress.point(s) for s in sessions_newest_first if s["status"] in READY and s.get("set")]
    return progress.trend(list(reversed(pts[:6])))


def warnings_for(client: dict, sessions_newest_first: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    w: list[dict] = []
    ready = [s for s in sessions_newest_first if s["status"] in READY]
    if any((s.get("judgement") or {}).get("safety", {}).get("pain_reported") for s in ready[:3]):
        w.append({"code": "pain", "level": "red", "text": "Pain reported in a recent set"})
    if sessions_newest_first and sessions_newest_first[0]["status"] == "needs_reshoot":
        w.append({"code": "needs_reshoot", "level": "amber", "text": "Latest video needs a re-shoot"})
    if len(ready) >= 3 and latest_trend(sessions_newest_first) == "declining":
        w.append({"code": "form_dropping", "level": "amber", "text": "Form score is dropping"})
    last = as_utc(sessions_newest_first[0]["created_at"]) if sessions_newest_first else None
    if last is None:
        if client.get("profile_complete") and as_utc(client["created_at"]) < now - timedelta(days=NO_UPLOAD_DAYS):
            w.append({"code": "no_upload", "level": "amber", "text": "No uploads yet"})
    elif last < now - timedelta(days=NO_UPLOAD_DAYS):
        w.append({"code": "no_upload", "level": "amber", "text": f"No upload in {(now - last).days} days"})
    pending = sum(1 for s in sessions_newest_first if s["status"] == "ready_for_review")
    if pending:
        w.append({"code": "pending_review", "level": "info", "text": f"{pending} to review"})
    if not client.get("profile_complete"):
        w.append({"code": "profile_incomplete", "level": "info", "text": "Profile not filled in yet"})
    return w


def client_tz(client: dict) -> str:
    return (client.get("profile") or {}).get("timezone") or DEFAULT_TZ


def today_local(client: dict):
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(client_tz(client))).date()


__all__ = ["bmi", "client_safe_profile", "session_row", "build_series", "latest_trend", "warnings_for",
           "client_tz", "today_local", "local_date"]
