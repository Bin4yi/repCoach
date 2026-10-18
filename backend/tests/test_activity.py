"""GitHub-style dashboard maths: points, quartile levels, streaks, time zones, leap years, empty history."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.analysis.activity import build_activity, compute_streaks, level_for, level_thresholds, session_points

TODAY = date(2026, 10, 18)  # a Sunday


def sess(day: date, reps=10, sets=1, form=75, ex="squat", hour=12, tz=timezone.utc, status="ready_for_review", **extra):
    return {"created_at": datetime(day.year, day.month, day.day, hour, tzinfo=tz), "exercise": ex, "status": status,
            "inputs": {"sets_done_today": sets},
            "set": {"rep_count": reps, "form_score": form, "depth_mean": 90, "depth_best": 85}, **extra}


def days_of(a, offsets):
    return {a + timedelta(days=o) for o in offsets}


# ------------------------------------------------------------------ points & levels
def test_points_are_sets_times_reps_plus_form_bonus():
    assert session_points(sess(TODAY, reps=10, sets=3, form=70)) == 30
    assert session_points(sess(TODAY, reps=10, sets=3, form=85)) == 35
    assert session_points(sess(TODAY, reps=0, sets=3, form=85)) == 0


def test_level_thresholds_are_quartiles_of_nonzero_days():
    pts = [10, 20, 30, 40, 50, 60, 70, 80]
    th = level_thresholds(pts)
    assert th == pytest.approx([27.5, 45, 62.5])
    levels = [level_for(p, th, max(pts)) for p in pts]
    assert levels == [1, 1, 2, 2, 3, 3, 4, 4]
    assert level_for(0, th, 80) == 0


def test_beginner_with_few_days_still_gets_dark_squares():
    a = build_activity([sess(TODAY - timedelta(days=3), reps=5), sess(TODAY, reps=8)], today=TODAY)
    levels = {d["date"]: d["level"] for d in a["days"] if d["level"]}
    assert levels[TODAY.isoformat()] == 4
    assert 1 <= levels[(TODAY - timedelta(days=3)).isoformat()] <= 4
    single = build_activity([sess(TODAY)], today=TODAY)
    assert [d["level"] for d in single["days"]][-1] == 4


def test_empty_history():
    a = build_activity([], today=TODAY)
    assert len(a["days"]) == 365 and all(d["level"] == 0 and d["points"] == 0 for d in a["days"])
    assert a["streaks"] == {"current": 0, "longest": 0}
    assert a["totals"]["sessions"] == 0 and a["totals"]["avg_form_30d"] is None
    assert a["exercise_cards"] == [] and a["feed"] == [] and a["total_sets_last_year"] == 0
    assert not any(b["earned"] for b in a["badges"])


def test_queued_and_reshoot_sessions_do_not_count():
    a = build_activity([sess(TODAY, status="queued"), sess(TODAY, status="needs_reshoot")], today=TODAY)
    assert a["totals"]["sessions"] == 0


def test_day_bucket_contents_and_sets_last_year():
    ss = [sess(TODAY, reps=10, sets=2, form=82, ex="squat"), sess(TODAY, reps=8, sets=1, form=90, ex="pushup"),
          sess(TODAY - timedelta(days=400), reps=5)]
    a = build_activity(ss, today=TODAY)
    d = a["days"][-1]
    assert d["date"] == "2026-10-18" and d["reps"] == 28 and d["best_form"] == 90
    assert d["exercises"] == ["pushup", "squat"] and d["points"] == 20 + 5 + 8 + 5
    assert a["total_sets_last_year"] == 3          # the 400-day-old session is outside the window
    assert a["totals"]["sessions"] == 3


# ------------------------------------------------------------------ streaks
def test_streak_every_day_plan_breaks_on_gap():
    train = days_of(TODAY, [-6, -5, -4, -2, -1, 0])   # gap at -3
    cur, longest, _ = compute_streaks(train, TODAY, days_per_week=7)
    assert (cur, longest) == (3, 3)


def test_streak_allows_planned_rest_days():
    # trains Mon, Wed, Fri with a 3-day plan: rest days in between do not break the streak
    train = {date(2026, 10, 12), date(2026, 10, 14), date(2026, 10, 16)}
    cur, longest, runs = compute_streaks(train, TODAY, days_per_week=3)
    assert (cur, longest) == (5, 5) and runs == [(date(2026, 10, 12), date(2026, 10, 16))]
    # the same pattern on a train-every-day plan is three separate 1-day streaks
    assert compute_streaks(train, TODAY, days_per_week=7)[:2] == (0, 1)


def test_streak_today_without_training_is_not_a_break():
    train = days_of(TODAY, [-3, -2, -1])
    assert compute_streaks(train, TODAY, 7)[0] == 3
    assert compute_streaks(train | {TODAY}, TODAY, 7)[0] == 4


def test_long_gap_breaks_streak_even_with_rest_days():
    train = {date(2026, 10, 1), date(2026, 10, 10)}
    cur, longest, _ = compute_streaks(train, TODAY, 3)
    assert cur == 0 and longest == 1


def test_streak_empty_and_future_safe():
    assert compute_streaks(set(), TODAY, 3) == (0, 0, [])
    assert compute_streaks({TODAY + timedelta(days=5)}, TODAY, 3) == (0, 0, [])


def test_longest_streak_survives_after_current_resets():
    old = days_of(date(2026, 8, 1), range(10))
    a = build_activity([sess(d) for d in old], today=TODAY, training_days_per_week=7)
    assert a["streaks"] == {"current": 0, "longest": 10}
    assert next(b for b in a["badges"] if b["code"] == "streak_7")["earned"]
    assert not next(b for b in a["badges"] if b["code"] == "streak_30")["earned"]
    assert any(i["text"] == "7-day streak!" for g in a["feed"] for i in g["items"])


# ------------------------------------------------------------------ time zones
def test_day_boundary_uses_client_time_zone():
    # 20:00 UTC on Oct 17 is 01:30 on Oct 18 in Colombo (UTC+5:30) but still Oct 17 in UTC / Los Angeles
    s = sess(date(2026, 10, 17), hour=20)
    colombo = build_activity([s], tz="Asia/Colombo", today=TODAY)
    assert colombo["days"][-1]["points"] > 0
    utc = build_activity([s], tz="UTC", today=TODAY)
    assert utc["days"][-1]["points"] == 0 and utc["days"][-2]["points"] > 0
    la = build_activity([s], tz="America/Los_Angeles", today=TODAY)
    assert la["days"][-2]["points"] > 0


def test_naive_datetimes_are_treated_as_utc():
    s = sess(TODAY)
    s["created_at"] = s["created_at"].replace(tzinfo=None)
    assert build_activity([s], today=TODAY)["days"][-1]["points"] > 0


# ------------------------------------------------------------------ leap year
def test_leap_day_is_a_real_bucket():
    today = date(2028, 3, 1)
    a = build_activity([sess(date(2028, 2, 29))], today=today, tz="UTC")
    dates = [d["date"] for d in a["days"]]
    assert len(dates) == 365 and dates[-1] == "2028-03-01" and dates[0] == "2027-03-03"
    assert "2028-02-29" in dates
    assert a["days"][dates.index("2028-02-29")]["points"] > 0
    assert len(set(dates)) == 365


def test_non_leap_year_has_no_feb_29():
    a = build_activity([], today=date(2027, 3, 1), tz="UTC")
    assert "2027-02-29" not in [d["date"] for d in a["days"]]


# ------------------------------------------------------------------ cards, feed, badges
def test_exercise_cards_feed_and_badges():
    ss = []
    for i in range(12):
        ss.append(sess(TODAY - timedelta(days=60 - i * 5), form=70 + i * 2, ex="squat"))
    ss[-1]["set"]["form_score"] = 92
    ss[-1]["set"]["depth_best"] = 70            # new best depth
    ss[-1]["set"]["depth_mean"] = 78            # more than 10% deeper than the first session's 90
    ss.append(sess(TODAY - timedelta(days=2), ex="pushup", status="approved",
                   approved_at=datetime(2026, 10, 17, 12, tzinfo=timezone.utc)))
    a = build_activity(ss, today=TODAY)
    cards = {c["exercise"]: c for c in a["exercise_cards"]}
    assert cards["squat"]["sessions"] == 12 and cards["squat"]["best_form"] == 92
    assert len(cards["squat"]["sparkline"]) == 12 and cards["pushup"]["color"]
    texts = [i["text"] for g in a["feed"] for i in g["items"]]
    assert "New best squat depth" in texts and "Coach approved your report" in texts
    assert any(t.startswith("Uploaded a squat set (10 reps, form 92)") for t in texts)
    oct_group = next(g for g in a["feed"] if g["month"] == "2026-10")
    assert oct_group["summary"].startswith("October 2026: ")
    earned = {b["code"] for b in a["badges"] if b["earned"]}
    assert {"first_upload", "form_90", "depth_10"} <= earned and "sessions_100" not in earned
    assert a["totals"]["training_since"] == "2026-08"


def test_hundred_sessions_badge():
    ss = [sess(TODAY - timedelta(days=i // 2), ex="squat") for i in range(100)]
    a = build_activity(ss, today=TODAY)
    assert next(b for b in a["badges"] if b["code"] == "sessions_100")["earned"]


def test_avg_form_last_30_days():
    ss = [sess(TODAY - timedelta(days=1), form=80), sess(TODAY - timedelta(days=2), form=60),
          sess(TODAY - timedelta(days=45), form=10)]
    assert build_activity(ss, today=TODAY)["totals"]["avg_form_30d"] == 70.0
