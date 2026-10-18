"""Rule-based judgement: profile + per-video inputs + metrics + history -> one object (no LLM involved).

The LLM only explains this object; every safety decision is made here.
"""
from __future__ import annotations

from . import progress

MAX_WEEKLY_LOAD_INCREASE_PCT = 5.0    # normal progression cap per week
CONSERVATIVE_AGE = 65
CLOSE_TO_FAILURE_VELOCITY_LOSS = 20.0  # % concentric slowdown
CLOSE_TO_FAILURE_RPE = 8
BEGINNER_CUE_LIMIT, DEFAULT_CUE_LIMIT = 2, 3

# Words in the injury note that relate to each exercise (simple keyword match, not diagnosis).
INJURY_KEYWORDS = {
    "squat": ["knee", "hip", "back", "spine", "ankle", "leg", "hamstring", "quad", "groin"],
    "pushup": ["shoulder", "wrist", "elbow", "chest", "pec", "arm", "back", "neck", "hand"],
    "bicep_curl": ["elbow", "wrist", "shoulder", "bicep", "arm", "forearm", "hand", "tendon"],
}


def injury_relates(injuries: str | None, exercise: str) -> bool:
    if not injuries:
        return False
    text = injuries.lower()
    return any(k in text for k in INJURY_KEYWORDS.get(exercise, []))


def build_judgement(profile: dict, inputs: dict, analysis: dict, quality: dict | None,
                    history_points: list[dict] | None = None) -> dict:
    """
    profile:  client profile dict (age, goal, experience_level, injuries_or_limits, body_weight_kg ...)
    inputs:   per-video inputs dict (exercise, load_kg, rpe, pain_during_set ...)
    analysis: {"flags": [...], "set": {...}}
    quality:  QualityReport dict
    history_points: progress.point() dicts, newest first (earlier sessions only)
    """
    exercise = inputs["exercise"]
    set_m = analysis.get("set") or {}
    flags = analysis.get("flags") or []
    score = set_m.get("form_score")

    # fatigue = RPE + measured speed loss
    vloss = set_m.get("velocity_loss_pct")
    rpe = inputs.get("rpe")
    close = bool(vloss is not None and rpe is not None
                 and vloss >= CLOSE_TO_FAILURE_VELOCITY_LOSS and rpe >= CLOSE_TO_FAILURE_RPE)
    fatigue = {"velocity_loss_pct": vloss, "rpe": rpe, "close_to_failure": close}

    # relative strength
    bw = inputs.get("body_weight_today_kg") or profile.get("body_weight_kg")
    load = inputs.get("load_kg") or 0
    relative_load = round(load / bw, 2) if bw else None

    # safety
    reasons: list[str] = []
    pain = bool(inputs.get("pain_during_set"))
    if pain:
        reasons.append("Client reported pain during the set.")
    if (profile.get("age") or 0) >= CONSERVATIVE_AGE:
        reasons.append(f"Client age is {profile['age']} (65 or older).")
    if injury_relates(profile.get("injuries_or_limits"), exercise):
        reasons.append("Listed injury or limit may relate to this exercise.")
    if profile.get("goal") == "rehab_return":
        reasons.append("Goal is returning to training after rehab.")
    dq_ok = bool(quality.get("ok", True)) if quality else True
    dq_notes = list((quality or {}).get("notes", []))
    if quality and quality.get("reason"):
        dq_notes.append(quality["reason"])
    if not dq_ok:
        reasons.append("Video quality was poor, so measurements are uncertain.")
    elif quality and quality.get("avg_visibility", 1) < 0.6:
        reasons.append("Video quality was poor, so measurements are uncertain.")
        dq_ok = False
    conservative = bool(reasons)

    # progress vs the last 3 sessions of the same exercise
    current = {"exercise": exercise, "form_score": score, "depth": set_m.get("depth_mean"),
               "relative_load": relative_load}
    prog = progress.compare_with_last_n(current, history_points or [], n=3)

    return {
        "exercise": exercise,
        "form_score": score,
        "flags": [{k: f[k] for k in ("code", "severity", "reps", "evidence")} for f in flags],
        "fatigue": fatigue,
        "relative_load": relative_load,
        "safety": {"pain_reported": pain, "conservative_mode": conservative, "reasons": reasons},
        "progress_vs_last_3": prog,
        "data_quality": {"ok": dq_ok, "notes": dq_notes},
        # rules the plan generator must respect (enforced in code, not by the LLM)
        "max_load_increase_pct": 0.0 if conservative else MAX_WEEKLY_LOAD_INCREASE_PCT,
        "cue_limit": BEGINNER_CUE_LIMIT if profile.get("experience_level") == "beginner" else DEFAULT_CUE_LIMIT,
        "coach_attention": pain or conservative or any(f["severity"] == "high" for f in flags),
    }
