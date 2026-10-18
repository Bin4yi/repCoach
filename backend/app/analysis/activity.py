"""GitHub-style training dashboard data, computed from sessions. No LLM.

Day boundaries use the client's own time zone (default Asia/Colombo).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from ..models.schemas import EXERCISE_LABELS

DEFAULT_TZ = "Asia/Colombo"
WINDOW_DAYS = 365
FORM_BONUS = 5          # extra training points for a set with form score >= FORM_BONUS_MIN
FORM_BONUS_MIN = 80
BEST_DEPTH_MIN_GAIN_DEG = 2.0
EXERCISE_COLORS = {"squat": "#1d1d1f", "pushup": "#ff9500", "bicep_curl": "#34c759"}
COUNTED_STATUSES = {"ready_for_review", "approved"}


def as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def local_date(dt: datetime, tz: str) -> date:
    return as_utc(dt).astimezone(ZoneInfo(tz)).date()


# --------------------------------------------------------------------------- points & levels
def session_sets(s: dict) -> int:
    return int((s.get("inputs") or {}).get("sets_done_today") or 1)


def session_points(s: dict) -> int:
    reps = (s.get("set") or {}).get("rep_count") or 0
    score = (s.get("set") or {}).get("form_score")
    pts = session_sets(s) * reps
    if pts and score is not None and score >= FORM_BONUS_MIN:
        pts += FORM_BONUS
    return pts


def level_thresholds(points: list[float]) -> list[float]:
    """Quartiles of the client's own non-zero days (like GitHub), so beginners also get dark squares."""
    if not points:
        return [0, 0, 0]
    return [float(x) for x in np.percentile(points, [25, 50, 75])]


def level_for(points: float, thresholds: list[float], max_points: float) -> int:
    if points <= 0:
        return 0
    if points >= max_points:
        return 4                       # the best day is always the darkest square
    return 1 + sum(points > t for t in thresholds)


# --------------------------------------------------------------------------- streaks
def compute_streaks(train_days: set[date], today: date, days_per_week: int) -> tuple[int, int, list[tuple[date, date]]]:
    """Return (current, longest, runs).

    A streak is a run of calendar days. A day without training does NOT break it as long as the number of
    non-training days in any 7-day window inside the run stays within the planned rest days
    (7 - training_days_per_week). A streak ends on its last training day. Today without training is not
    counted against the client yet (the day is still going).
    """
    if not train_days:
        return 0, 0, []
    allowed_rest = max(0, 7 - max(1, min(7, days_per_week)))
    end = today if today in train_days else today - timedelta(days=1)
    first = min(train_days)
    if end < first:
        return 0, 0, []

    runs: list[tuple[date, date]] = []
    run_start: date | None = None
    last_train: date | None = None
    d = first
    while d <= end:
        trained = d in train_days
        if run_start is None:
            if trained:
                run_start = last_train = d
        else:
            window_start = max(run_start, d - timedelta(days=6))
            misses = sum(1 for k in range((d - window_start).days + 1)
                         if (window_start + timedelta(days=k)) not in train_days)
            if trained:
                last_train = d
            if misses > allowed_rest:
                runs.append((run_start, last_train))
                run_start = last_train = None
                if trained:
                    run_start = last_train = d
        d += timedelta(days=1)
    current = 0
    if run_start is not None:
        runs.append((run_start, last_train))
        current = (last_train - run_start).days + 1
    longest = max(((b - a).days + 1 for a, b in runs), default=0)
    return current, longest, runs


# --------------------------------------------------------------------------- main builder
def build_activity(sessions: list[dict], tz: str = DEFAULT_TZ, training_days_per_week: int = 3,
                   today: date | None = None, client_created: datetime | None = None) -> dict:
    tz = tz or DEFAULT_TZ
    today = today or datetime.now(ZoneInfo(tz)).date()
    rows = sorted((dict(s) for s in sessions if s.get("status") in COUNTED_STATUSES and s.get("set")),
                  key=lambda s: as_utc(s["created_at"]))
    for s in rows:
        s["_day"] = local_date(s["created_at"], tz)

    start = today - timedelta(days=WINDOW_DAYS - 1)
    by_day: dict[date, list[dict]] = defaultdict(list)
    for s in rows:
        by_day[s["_day"]].append(s)

    pts_by_day = {d: sum(session_points(s) for s in ss) for d, ss in by_day.items()}
    window_pts = [p for d, p in pts_by_day.items() if start <= d <= today and p > 0]
    thresholds = level_thresholds(window_pts)
    max_pts = max(window_pts, default=0)

    days = []
    for k in range(WINDOW_DAYS):
        d = start + timedelta(days=k)
        ss = by_day.get(d, [])
        p = pts_by_day.get(d, 0)
        scores = [s["set"]["form_score"] for s in ss if s["set"].get("form_score") is not None]
        days.append({
            "date": d.isoformat(), "level": level_for(p, thresholds, max_pts), "points": p,
            "exercises": sorted({s["exercise"] for s in ss}),
            "reps": sum(session_sets(s) * (s["set"].get("rep_count") or 0) for s in ss),
            "best_form": max(scores) if scores else None,
        })

    train_days = set(by_day)
    current, longest, runs = compute_streaks(train_days, today, training_days_per_week)

    last30 = [s["set"]["form_score"] for s in rows
              if today - timedelta(days=29) <= s["_day"] <= today and s["set"].get("form_score") is not None]
    in_window = [s for s in rows if start <= s["_day"] <= today]
    first_day = rows[0]["_day"] if rows else None
    if client_created:
        cd = local_date(client_created, tz)
        first_day = min(cd, first_day) if first_day else cd
    totals = {
        "sessions": len(rows),
        "reps": sum(session_sets(s) * (s["set"].get("rep_count") or 0) for s in rows),
        "avg_form_30d": round(float(np.mean(last30)), 1) if last30 else None,
        "training_since": first_day.strftime("%Y-%m") if first_day else None,
        "sets_last_year": sum(session_sets(s) for s in in_window),
    }

    cards = _exercise_cards(rows)
    feed = _feed(rows, runs, tz)
    badges = _badges(rows, longest, runs)
    return {"timezone": tz, "today": today.isoformat(), "days": days,
            "total_sets_last_year": totals["sets_last_year"],
            "streaks": {"current": current, "longest": longest}, "totals": totals,
            "thresholds": [round(t, 1) for t in thresholds],
            "exercise_cards": cards, "feed": feed, "badges": badges}


def _exercise_cards(rows: list[dict]) -> list[dict]:
    by_ex: dict[str, list[dict]] = defaultdict(list)
    for s in rows:
        by_ex[s["exercise"]].append(s)
    cards = []
    for ex, ss in by_ex.items():
        scores = [s["set"]["form_score"] for s in ss if s["set"].get("form_score") is not None]
        cards.append({"exercise": ex, "label": EXERCISE_LABELS.get(ex, ex), "color": EXERCISE_COLORS.get(ex, "#64748b"),
                      "sessions": len(ss), "best_form": max(scores) if scores else None,
                      "sparkline": scores[-20:], "last_date": ss[-1]["_day"].isoformat()})
    return sorted(cards, key=lambda c: c["last_date"], reverse=True)


def _feed(rows: list[dict], runs: list[tuple[date, date]], tz: str) -> list[dict]:
    items: list[dict] = []
    best: dict[str, float] = {}
    for s in rows:
        ex, label = s["exercise"], EXERCISE_LABELS.get(s["exercise"], s["exercise"]).lower()
        m = s["set"]
        score = m.get("form_score")
        items.append({"date": s["_day"].isoformat(), "type": "upload", "exercise": ex,
                      "text": f"Uploaded a {label} set ({m.get('rep_count', 0)} reps"
                              + (f", form {score}" if score is not None else "") + ")"})
        depth = m.get("depth_best")
        if depth is not None:
            prev = best.get(ex)
            if prev is not None and prev - depth >= BEST_DEPTH_MIN_GAIN_DEG:
                items.append({"date": s["_day"].isoformat(), "type": "best_depth", "exercise": ex,
                              "text": f"New best {label} depth"})
            best[ex] = depth if prev is None else min(prev, depth)
        if s.get("status") == "approved" and s.get("approved_at"):
            items.append({"date": local_date(s["approved_at"], tz).isoformat(), "type": "approved",
                          "exercise": ex, "text": "Coach approved your report"})
    for a, b in runs:
        length = (b - a).days + 1
        for n in (7, 30):
            if length >= n:
                items.append({"date": (a + timedelta(days=n - 1)).isoformat(), "type": "streak",
                              "exercise": None, "text": f"{n}-day streak!"})
    items.sort(key=lambda i: i["date"], reverse=True)

    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        groups[it["date"][:7]].append(it)
    out = []
    for ym in sorted(groups, reverse=True):
        its = groups[ym]
        uploads = [i for i in its if i["type"] == "upload"]
        n_ex = len({i["exercise"] for i in uploads})
        label = datetime.strptime(ym + "-01", "%Y-%m-%d").strftime("%B %Y")
        out.append({"month": ym, "label": label, "sessions": len(uploads), "exercises": n_ex,
                    "summary": f"{label}: {len(uploads)} session{'s' if len(uploads) != 1 else ''}, "
                               f"{n_ex} exercise{'s' if n_ex != 1 else ''}",
                    "items": its[:30]})
    return out


def _badges(rows: list[dict], longest: int, runs: list[tuple[date, date]]) -> list[dict]:
    scores = [(s["_day"], s["set"]["form_score"]) for s in rows if s["set"].get("form_score") is not None]
    first90 = next((d for d, sc in scores if sc >= 90), None)
    # depth improved 10%: best depth of an exercise vs its first session
    improved = None
    by_ex: dict[str, list[dict]] = defaultdict(list)
    for s in rows:
        if s["set"].get("depth_mean"):
            by_ex[s["exercise"]].append(s)
    for ss in by_ex.values():
        first = ss[0]["set"]["depth_mean"]
        for s in ss[1:]:
            if (first - s["set"]["depth_mean"]) / first >= 0.10:
                d = s["_day"]
                improved = d if improved is None else min(improved, d)
                break
    run7 = next((a + timedelta(days=6) for a, b in runs if (b - a).days + 1 >= 7), None)
    run30 = next((a + timedelta(days=29) for a, b in runs if (b - a).days + 1 >= 30), None)

    def b(code, label, desc, on):
        return {"code": code, "label": label, "description": desc, "earned": on is not None,
                "earned_on": on.isoformat() if on else None}

    return [
        b("first_upload", "First upload", "Sent your first video", rows[0]["_day"] if rows else None),
        b("streak_7", "7-day streak", "Kept your plan going for 7 days", run7),
        b("streak_30", "30-day streak", "Kept your plan going for 30 days", run30),
        b("form_90", "Form 90+", "Scored 90 or more on a set", first90),
        b("sessions_100", "100 sessions", "Uploaded 100 sets", rows[99]["_day"] if len(rows) >= 100 else None),
        b("depth_10", "Depth improved 10%", "Moved deeper by 10% since your first set", improved),
    ]
