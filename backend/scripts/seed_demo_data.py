"""Create 3 DEMO clients with about a year of synthetic sessions.

All landmark sequences come from app/pose/synthetic.py (forward-kinematics skeletons), pushed through the REAL
analysis pipeline, so charts and the heatmap look real. Everything is labelled demo=True. Not real people.

    python -m scripts.seed_demo_data [--reset]
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analysis import progress  # noqa: E402
from app.analysis.judgement import build_judgement  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_db, now  # noqa: E402
from app.llm.reports import fallback_feedback, fallback_progress, profile_for_llm  # noqa: E402
from app.pipeline import analyze_sequence  # noqa: E402
from app.pose import synthetic as syn  # noqa: E402

TZ = ZoneInfo("Asia/Colombo")
WEEKS = 52

DEMO_CLIENTS = [
    {
        "key": "nimali", "token": "demo-nimali", "plan_days": 3, "start_weeks_ago": 40, "consistency": 0.75,
        "profile": {"name": "Nimali Fernando (demo)", "age": 24, "sex": "female", "height_cm": 163.0, "body_weight_kg": 71.0,
                    "experience_level": "beginner", "goal": "fat_loss", "training_days_per_week": 3,
                    "injuries_or_limits": None, "equipment": ["bodyweight", "dumbbells"], "timezone": "Asia/Colombo"},
        "weight": (71.0, 66.5), "exercises": ["squat", "pushup", "bicep_curl"],
        "squat_depth": (112, 92), "loads": {"squat": (0, 0), "pushup": (0, 0), "bicep_curl": (4, 8)},
        "coach_notes": "DEMO. Nervous at first, loves the app streaks. Check push-up hip sag.",
    },
    {
        "key": "kasun", "token": "demo-kasun", "plan_days": 4, "start_weeks_ago": 52, "consistency": 0.9,
        "profile": {"name": "Kasun Silva (demo)", "age": 31, "sex": "male", "height_cm": 178.0, "body_weight_kg": 82.0,
                    "experience_level": "intermediate", "goal": "strength", "training_days_per_week": 4,
                    "injuries_or_limits": None, "equipment": ["barbell", "dumbbells", "machines"], "timezone": "Asia/Colombo"},
        "weight": (80.0, 83.0), "exercises": ["squat", "squat", "pushup", "bicep_curl"],
        "squat_depth": (100, 78), "loads": {"squat": (70, 110), "pushup": (0, 0), "bicep_curl": (14, 22)},
        "coach_notes": "DEMO. Prepping for a local powerlifting meet. Long femurs: some forward lean is normal.",
    },
    {
        "key": "ranjan", "token": "demo-ranjan", "plan_days": 3, "start_weeks_ago": 30, "consistency": 0.8,
        "profile": {"name": "Ranjan de Mel (demo)", "age": 67, "sex": "male", "height_cm": 170.0, "body_weight_kg": 76.0,
                    "experience_level": "beginner", "goal": "rehab_return", "training_days_per_week": 3,
                    "injuries_or_limits": "Left knee replacement 8 months ago, mild stiffness in the morning",
                    "equipment": ["bodyweight", "bands"], "timezone": "Asia/Colombo"},
        "weight": (77.0, 75.0), "exercises": ["squat", "bicep_curl", "squat"],
        "squat_depth": (125, 104), "loads": {"squat": (0, 0), "pushup": (0, 0), "bicep_curl": (2, 5)},
        "coach_notes": "DEMO. Physio cleared light squats to a box. Always ask about the left knee first.",
        "pain_from_end": 3,   # pain reported in the 3rd newest session, so the coach dashboard shows a red warning
    },
]


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def make_sequence(exercise: str, spec: dict, t: float, rng: random.Random, tired: bool):
    """Synthetic skeleton whose quality improves with t (0 = first session, 1 = last)."""
    n = rng.randint(6, 10)
    slip = rng.random() < 0.22   # everyone has an off day: one random form slip so scores are not all 100
    if exercise == "squat":
        d0, d1 = spec["squat_depth"]
        base = lerp(d0, d1, t) + rng.uniform(-4, 4) + (16 if slip else 0)
        per_rep = [base + (i * 2.5 if tired else rng.uniform(-3, 3)) for i in range(n)]
        lean = lerp(52, 38, t) + rng.uniform(-3, 3) if spec["key"] != "kasun" else rng.uniform(44, 52)
        return syn.gen_squat(n_reps=n, min_knee_per_rep=per_rep, lean=lean, down_s=lerp(1.0, 2.2, t) + rng.uniform(-0.2, 0.2),
                             up_s=rng.uniform(0.9, 1.3), femur_ratio=1.15 if spec["key"] == "kasun" else 1.0,
                             noise=0.004, seed=rng.randint(0, 9999))
    if exercise == "pushup":
        return syn.gen_pushup(n_reps=n, min_elbow=lerp(105, 78, t) + rng.uniform(-5, 5),
                              hip_offset=lerp(0.11, 0.0, t) + rng.uniform(-0.01, 0.01) + (0.1 if slip else 0), noise=0.004, seed=rng.randint(0, 9999))
    return syn.gen_curl(n_reps=n, min_elbow=lerp(65, 42, t) + rng.uniform(-4, 4), drift_deg=lerp(30, 8, t) + (22 if slip else 0),
                        swing_deg=lerp(14, 4, t), noise=0.004, seed=rng.randint(0, 9999))


def training_days(spec: dict, today: date, rng: random.Random) -> list[date]:
    start = today - timedelta(weeks=spec["start_weeks_ago"])
    plan = spec["plan_days"]
    patterns = {3: [0, 2, 4], 4: [0, 1, 3, 4]}
    days = []
    d = start
    holiday = (today - timedelta(weeks=rng.randint(14, 20)), 12)   # a ~12 day break so the heatmap has a gap
    while d <= today:
        in_holiday = holiday[0] <= d < holiday[0] + timedelta(days=holiday[1])
        if d.weekday() in patterns.get(plan, [0, 2, 4]) and not in_holiday and rng.random() < spec["consistency"]:
            days.append(d)
        d += timedelta(days=1)
    return days


async def seed(db, reset: bool = False, seed_value: int = 7) -> dict[str, str]:
    """Insert demo data. Returns {client_key: token}. No-op for clients that already exist."""
    rng = random.Random(seed_value)
    if reset:
        ids = [c["_id"] async for c in db.clients.find({"demo": True})]
        await db.clients.delete_many({"demo": True})
        for coll in (db.sessions, db.weight_log, db.plans):
            await coll.delete_many({"client_id": {"$in": ids}})
    today = datetime.now(TZ).date()
    tokens = {}
    for spec in DEMO_CLIENTS:
        tokens[spec["key"]] = spec["token"]
        if await db.clients.find_one({"token": spec["token"]}):
            continue
        cid = f"demo-{spec['key']}"
        created = datetime.combine(today - timedelta(weeks=spec["start_weeks_ago"]), datetime.min.time(), tzinfo=TZ)
        await db.clients.insert_one({"_id": cid, "token": spec["token"], "name": spec["profile"]["name"],
                                     "profile": spec["profile"], "profile_complete": True, "coach_notes": spec["coach_notes"],
                                     "consent_at": created.astimezone(timezone.utc), "created_at": created.astimezone(timezone.utc),
                                     "demo": True})
        days = training_days(spec, today, rng)
        # weekly weight log
        w0, w1 = spec["weight"]
        weeks = spec["start_weeks_ago"]
        for k in range(0, weeks + 1, 2):
            d = today - timedelta(weeks=weeks - k)
            await db.weight_log.insert_one({"_id": f"{cid}-w{k}", "client_id": cid, "demo": True, "date": d.isoformat(),
                                            "kg": round(lerp(w0, w1, k / max(weeks, 1)) + rng.uniform(-0.3, 0.3), 1),
                                            "created_at": created.astimezone(timezone.utc)})
        history: dict[str, list[dict]] = {}
        docs = []
        for i, d in enumerate(days):
            t = i / max(len(days) - 1, 1)
            exercise = spec["exercises"][i % len(spec["exercises"])]
            tired = rng.random() < 0.25
            seq = make_sequence(exercise, spec, t, rng, tired)
            analysis = analyze_sequence(seq, exercise, "side", spec["profile"]["experience_level"])
            if analysis["quality"]["needs_reshoot"] or not analysis["set"]:
                continue
            l0, l1 = spec["loads"][exercise]
            load = round(lerp(l0, l1, t) / 2.5) * 2.5 if l1 else 0.0
            pain = spec.get("pain_from_end") == len(days) - i
            inputs = {"exercise": exercise, "camera_view": "side", "load_kg": load, "target_reps": 8,
                      "sets_done_today": rng.choice([2, 3, 3, 4]), "rpe": rng.choice([6, 7, 7, 8, 9]),
                      "pain_during_set": pain, "pain_text": "twinge in left knee" if pain else None,
                      "body_weight_today_kg": None, "client_comment": None}
            hist_pts = list(reversed([progress.point(x) for x in history.get(exercise, [])]))
            judgement = build_judgement(spec["profile"], inputs, analysis, analysis["quality"], hist_pts)
            payload = {"judgement": judgement, "set_summary": analysis["set"]}
            fb = fallback_feedback(payload).model_dump()
            hist_summary = progress.history_summary(
                [{"exercise": exercise, "form_score": judgement["form_score"], "depth": analysis["set"]["depth_mean"],
                  "relative_load": judgement["relative_load"]}] + hist_pts)
            prog = fallback_progress({"history": hist_summary, "safety": judgement["safety"]}).model_dump()
            hour, minute = rng.choice([(7, 15), (8, 0), (17, 30), (18, 10), (19, 0)])
            at = datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ).astimezone(timezone.utc)
            doc = {"_id": f"{cid}-s{i:03d}", "client_id": cid, "demo": True, "exercise": exercise, "inputs": inputs,
                   "status": "approved", "created_at": at, "quality": analysis["quality"], "reps": analysis["reps"],
                   "flags": analysis["flags"], "set": analysis["set"], "extras": analysis["extras"], "side": analysis["side"],
                   "view": "side", "judgement": judgement, "video_deleted": True, "overlay_available": False,
                   "ai_feedback": {"draft": fb, "source": "demo-template", "warnings": [], "progress_draft": prog,
                                   "progress_source": "demo-template", "model": None},
                   "approved": {"client_message": fb["client_message"], "progress_message": prog["client_message"],
                                "coach_note": None, "approved_at": at + timedelta(hours=3)},
                   "approved_at": at + timedelta(hours=3)}
            docs.append(doc)
            history.setdefault(exercise, []).insert(0, doc)
        # the two newest sessions wait for coach review so the demo has something to approve
        for doc in docs[-2:]:
            doc["status"], doc["approved"], doc["approved_at"] = "ready_for_review", None, None
        if docs:
            await db.sessions.insert_many(docs)
    return tokens


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete existing demo data first")
    args = ap.parse_args()
    settings = get_settings()
    if settings.mongodb_uri.startswith("mongomock"):
        print("MONGODB_URI is mongomock:// (in-memory). Use DEMO_SEED_ON_START=true instead, or point at a real Mongo.")
        return
    _, db = await init_db(settings)
    tokens = await seed(db, reset=args.reset)
    print("Demo data ready (labelled demo). Client links:")
    for k, t in tokens.items():
        print(f"  {k:8s} {settings.frontend_url}/c/{t}")
    print("DEMO tokens are fixed and guessable. Never seed demo data into a production database.")


if __name__ == "__main__":
    asyncio.run(main())
