"""Generate feedback, progress summary and next-week plan with Gemma, with code-side safety checks.

Flow for each task: build payload (numbers only) -> ask Gemma -> validate (invented numbers, banned topics,
word limits, safety wording) -> regenerate once -> fall back to a plain template. Nothing here is shown to a
client until the coach approves it.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any, Callable, Protocol, TypeVar

from pydantic import BaseModel

from ..models.schemas import EXERCISE_LABELS, EXERCISES
from . import prompts
from .ollama_client import OllamaError
from .schemas import ProgressSummary, SessionFeedback, WeekPlan

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

CLIENT_MESSAGE_MAX_WORDS = 120
MAX_DELOAD_PCT = -20.0
PAIN_SENTENCE = ("You told us you felt pain during this set. Please stop this exercise for now and talk to "
                 "your coach before you train it again.")
CONSERVATIVE_SENTENCE = "Your coach will check this with you before any change in weight."
BANNED = re.compile(r"\b(calorie|calories|kcal|diet|dieting|macros?|protein intake|weigh(?:t)? loss|lose weight|"
                    r"fasting|keto|carbs?)\b", re.I)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
# Plain-language reading guide sent with every payload (no digits, so it never trips the number check).
READING_GUIDE = ("depth values are joint angles at the bottom of a rep: a LOWER angle means a DEEPER rep, which is "
                 "usually better. A negative depth change means the client went deeper. Form score is out of one hundred.")


class LLM(Protocol):
    async def chat_json(self, system: str, user: str, model_cls: type[T]) -> T: ...


# --------------------------------------------------------------------------- payload helpers
def profile_for_llm(profile: dict) -> dict:
    """Profile facts the model may see. NO name (the model says 'the client'), no coach notes."""
    keys = ("age", "sex", "height_cm", "body_weight_kg", "experience_level", "goal",
            "training_days_per_week", "injuries_or_limits", "equipment")
    return {k: profile.get(k) for k in keys if profile.get(k) not in (None, [], "")}


def _flatten_numbers(obj: Any, out: set[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        if not (isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj))):
            out.add(float(obj))
    elif isinstance(obj, str):
        out.update(float(x) for x in NUMBER_RE.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _flatten_numbers(v, out)


def invented_numbers(texts: list[str], payload: dict) -> list[str]:
    """Numbers that appear in the generated text but nowhere in the input data (rounding tolerance 0.5)."""
    allowed: set[float] = set()
    _flatten_numbers(payload, allowed)
    bad = []
    for text in texts:
        for tok in NUMBER_RE.findall(text or ""):
            n = float(tok)
            if not any(abs(n - a) <= 0.5 for a in allowed):
                bad.append(tok)
    return sorted(set(bad))


def _words(text: str) -> int:
    return len(text.split())


# --------------------------------------------------------------------------- generic generate-validate loop
async def _generate(llm: LLM | None, system: str, user: str, model_cls: type[T],
                    validate: Callable[[T], list[str]], fallback: Callable[[], T]) -> tuple[T, str, list[str]]:
    """Returns (object, source, warnings). source is 'gemma' or 'template'."""
    warnings: list[str] = []
    if llm is None:
        return fallback(), "template", ["AI model not available; used a template message."]
    prompt = user
    for attempt in range(2):  # first try + one regeneration
        try:
            obj = await llm.chat_json(system, prompt, model_cls)
        except OllamaError as exc:
            log.warning("Ollama failed: %s", exc)
            warnings.append("AI model did not answer; used a template message.")
            return fallback(), "template", warnings
        problems = validate(obj)
        if not problems:
            return obj, "gemma", warnings
        warnings.append(f"Attempt {attempt + 1} rejected: " + "; ".join(problems))
        prompt = user + prompts.retry_suffix(problems)
    warnings.append("AI answer failed the safety/number checks twice; used a template message.")
    return fallback(), "template", warnings


# --------------------------------------------------------------------------- 1. session feedback
CUE_LIBRARY = {
    "shallow_depth": ("Sit a little deeper in each squat", "Going deeper trains the legs through a fuller range."),
    "excess_forward_lean": ("Keep your chest tall as you go down", "A very forward lean puts more load on the lower back."),
    "knee_cave": ("Push your knees out in line with your toes", "Knees that collapse inward are harder to control."),
    "depth_drops_with_fatigue": ("Stop the set when your depth starts to shrink", "Form usually slips when you are tired."),
    "rushed_eccentric": ("Lower yourself slowly, about two to three seconds", "A slow descent builds control and strength."),
    "partial_range": ("Use the full range of motion", "Moving through the full range works the muscle better."),
    "hip_sag": ("Squeeze your belly and glutes so your body stays in one line", "Sagging hips strain the lower back."),
    "hips_high": ("Lower your hips so your body is one straight line", "Piked hips take work away from the chest and arms."),
    "no_lockout": ("Straighten your arms fully at the top", "A full lockout completes each rep."),
    "elbow_drift": ("Keep your elbows pinned beside your ribs", "Moving the elbows forward lets the shoulders take over."),
    "body_swing": ("Stand tall and do not rock your body", "Swinging means momentum, not your arms, lifts the weight."),
}


def code_notes(judgement: dict) -> list[str]:
    """Facts the coach must see, written by code (so they never depend on the model)."""
    notes = []
    s = judgement["safety"]
    if s["pain_reported"]:
        notes.append("PAIN REPORTED by the client during this set. No load increase. Please follow up before the next session.")
    for r in s["reasons"]:
        if not r.startswith("Client reported pain"):
            notes.append(r)
    if judgement["fatigue"]["close_to_failure"]:
        notes.append("Close to failure: rep speed dropped and RPE was high.")
    if not judgement["data_quality"]["ok"]:
        notes.append("Video quality was poor; treat the numbers with care.")
    return notes


def fallback_feedback(payload: dict) -> SessionFeedback:
    j = payload["judgement"]
    ex = EXERCISE_LABELS.get(j["exercise"], j["exercise"]).lower()
    reps = payload.get("set_summary", {}).get("rep_count")
    limit = j.get("cue_limit", 3)
    cues = []
    for f in j["flags"]:
        if f["code"] in CUE_LIBRARY and len(cues) < limit:
            c, why = CUE_LIBRARY[f["code"]]
            cues.append({"cue": c, "why": why, "reps": f["reps"]})
    well = ["You completed the set and the video was measured."] if not j["flags"] else []
    if j["form_score"] is not None and j["form_score"] >= 80:
        well.append(f"Your form score was {j['form_score']}, which is solid.")
    parts = [f"Thanks for sending your {ex} set" + (f" ({reps} reps)." if reps else ".")]
    if j["safety"]["pain_reported"]:
        parts.append(PAIN_SENTENCE)
    else:
        parts += [c["cue"] + "." for c in cues] or ["Your form looked good, keep it up."]
        if j["safety"]["conservative_mode"]:
            parts.append(CONSERVATIVE_SENTENCE)
    return SessionFeedback(
        summary=f"{ex.capitalize()} set with form score {j['form_score']}." if j["form_score"] is not None
        else f"{ex.capitalize()} set analysed.",
        what_went_well=well, fix_next_time=cues, coach_only_notes=code_notes(j),
        client_message=" ".join(parts))


def _enforce_feedback_safety(fb: SessionFeedback, judgement: dict) -> SessionFeedback:
    """Code-side guarantees that do not depend on what the model wrote."""
    limit = judgement.get("cue_limit", 3)
    fb.fix_next_time = fb.fix_next_time[:limit]
    allowed_reps = {r for f in judgement["flags"] for r in f["reps"]}
    for c in fb.fix_next_time:
        c.reps = [r for r in c.reps if r in allowed_reps]
    msg = fb.client_message.strip()
    safety = judgement["safety"]
    if safety["pain_reported"]:
        low = msg.lower()
        if not ("stop" in low and "coach" in low):
            msg = f"{PAIN_SENTENCE} {msg}" if _words(msg) + _words(PAIN_SENTENCE) <= CLIENT_MESSAGE_MAX_WORDS else PAIN_SENTENCE
    # coach notes written by code always come first
    existing = [n for n in fb.coach_only_notes if n not in code_notes(judgement)]
    fb.coach_only_notes = code_notes(judgement) + existing
    fb.client_message = msg
    return fb


def _validate_feedback(fb: SessionFeedback, payload: dict) -> list[str]:
    j = payload["judgement"]
    problems = []
    texts = [fb.summary, fb.client_message, *fb.what_went_well, *fb.coach_only_notes,
             *[c.cue + " " + c.why for c in fb.fix_next_time]]
    bad = invented_numbers(texts, payload)
    if bad:
        problems.append(f"These numbers are not in the data: {', '.join(bad)}. Remove or replace them.")
    if _words(fb.client_message) > CLIENT_MESSAGE_MAX_WORDS:
        problems.append(f"client_message has {_words(fb.client_message)} words; the maximum is {CLIENT_MESSAGE_MAX_WORDS}.")
    if BANNED.search(" ".join(texts)):
        problems.append("Do not mention diet, calories or weight loss.")
    if j["safety"]["pain_reported"] and re.search(r"\b(add|increase|heavier|more weight|extra weight)\b", fb.client_message, re.I):
        problems.append("Do not suggest adding load when pain was reported.")
    return problems


async def generate_feedback(llm: LLM | None, profile: dict, inputs: dict, judgement: dict, set_summary: dict) -> dict:
    payload = {"client": profile_for_llm(profile), "video_inputs": _inputs_for_llm(inputs),
               "judgement": judgement, "set_summary": set_summary, "how_to_read": READING_GUIDE}
    fb, source, warnings = await _generate(
        llm, prompts.SYSTEM_PROMPT, prompts.feedback_prompt(payload), SessionFeedback,
        lambda o: _validate_feedback(o, payload), lambda: fallback_feedback(payload))
    fb = _enforce_feedback_safety(fb, judgement)
    return {"draft": fb.model_dump(), "source": source, "warnings": warnings}


def _inputs_for_llm(inputs: dict) -> dict:
    keep = ("exercise", "camera_view", "load_kg", "target_reps", "sets_done_today", "rpe",
            "pain_during_set", "pain_text", "client_comment")
    return {k: inputs.get(k) for k in keep if inputs.get(k) not in (None, "")}


# --------------------------------------------------------------------------- 2. progress summary
def fallback_progress(payload: dict) -> ProgressSummary:
    h = payload["history"]
    trend = h["trend"]
    scores = [s for s in h["form_scores"] if s is not None]
    if trend == "not_enough_data":
        msg = "We need a few more sessions before we can see a clear pattern. Keep sending your sets!"
        return ProgressSummary(trend=trend, highlights=[], concerns=[], client_message=msg)
    high = [f"Form score went from {scores[0]} to {scores[-1]}."] if len(scores) >= 2 else []
    word = {"improving": "is getting better", "stable": "is steady", "declining": "has dipped a little"}[trend]
    msg = f"Your form {word} over your last sessions."
    if payload["safety"]["conservative_mode"]:
        msg += " " + CONSERVATIVE_SENTENCE
    concerns = ["Form scores are trending down."] if trend == "declining" else []
    return ProgressSummary(trend=trend, highlights=high, concerns=concerns, client_message=msg)


async def generate_progress(llm: LLM | None, profile: dict, history: dict, safety: dict) -> dict:
    payload = {"client": profile_for_llm(profile), "history": history, "safety": safety, "how_to_read": READING_GUIDE}

    def validate(o: ProgressSummary) -> list[str]:
        problems = []
        bad = invented_numbers([o.client_message, *o.highlights, *o.concerns], payload)
        if bad:
            problems.append(f"These numbers are not in the data: {', '.join(bad)}.")
        if _words(o.client_message) > CLIENT_MESSAGE_MAX_WORDS:
            problems.append("client_message is over 120 words.")
        if BANNED.search(" ".join([o.client_message, *o.highlights, *o.concerns])):
            problems.append("Do not mention diet, calories or weight loss.")
        return problems

    obj, source, warnings = await _generate(llm, prompts.SYSTEM_PROMPT, prompts.progress_prompt(payload),
                                            ProgressSummary, validate, lambda: fallback_progress(payload))
    obj.trend = history["trend"]  # the trend is computed in code; the model may not override it
    return {"draft": obj.model_dump(), "source": source, "warnings": warnings}


# --------------------------------------------------------------------------- 3. next-week plan
REPS_BY_GOAL = {"strength": "4-6", "muscle_gain": "8-12", "fat_loss": "10-15", "general_fitness": "8-12",
                "rehab_return": "8-10"}


def clamp_plan(plan: WeekPlan, last_loads: dict[str, float], max_increase_pct: float,
               days_per_week: int) -> tuple[WeekPlan, list[str]]:
    """Enforce plan rules in code: supported exercises, session count, and the weekly load-change cap."""
    notes: list[str] = []
    kept = []
    for s in plan.sessions:
        if s.exercise not in EXERCISES:
            notes.append(f"Removed unsupported exercise '{s.exercise}'.")
            continue
        kept.append(s)
    if len(kept) > days_per_week:
        notes.append(f"Trimmed to {days_per_week} sessions (client trains {days_per_week} days per week).")
        kept = kept[:days_per_week]
    for s in kept:
        pct = float(s.load_change_pct)
        clamped = max(MAX_DELOAD_PCT, min(max_increase_pct, pct))
        if clamped != pct:
            notes.append(f"{s.exercise}: load change {pct:+.1f}% clamped to {clamped:+.1f}%.")
        s.load_change_pct = round(clamped, 1)
        base = last_loads.get(s.exercise, 0.0)
        if base > 0:
            # round DOWN to the nearest 0.5 kg so rounding can never break the cap
            new = math.floor(base * (1 + clamped / 100) * 2) / 2
            if clamped == 0:
                s.load_suggestion = f"Stay at {base:g} kg"
            else:
                s.load_suggestion = f"{new:g} kg ({clamped:+.1f}% vs last session)"
        else:
            s.load_suggestion = ("Bodyweight. Progress with slower tempo or more reps, not extra load."
                                 if clamped <= 0 else "Bodyweight. Progress with slower tempo or more reps.")
    plan.sessions = kept
    return plan, notes


def fallback_plan(payload: dict) -> WeekPlan:
    c = payload["client"]
    days = c.get("training_days_per_week", 3)
    pool = payload.get("recent_exercises") or list(EXERCISES)
    spread = {1: [1], 2: [1, 4], 3: [1, 3, 5], 4: [1, 2, 4, 5], 5: [1, 2, 3, 5, 6], 6: [1, 2, 3, 4, 5, 6], 7: list(range(1, 8))}
    sessions = []
    for i, day in enumerate(spread[max(1, min(7, days))]):
        ex = pool[i % len(pool)]
        sessions.append({"day": day, "exercise": ex, "sets": 3, "reps": REPS_BY_GOAL.get(c.get("goal"), "8-12"),
                         "load_suggestion": "", "load_change_pct": 0.0, "tempo": "3-1-1",
                         "cue": payload.get("top_cues", {}).get(ex, "Controlled reps with full range.")})
    return WeekPlan(focus="Repeat last week with clean, controlled reps.", sessions=sessions,
                    progression_rule="Only add load when every set is clean and effort felt 7 or lower; the coach decides.",
                    coach_review_points=["Template plan (AI was not used). Please review loads and exercises."])


async def generate_plan(llm: LLM | None, profile: dict, recent: list[dict], conservative: bool,
                        reasons: list[str]) -> dict:
    """recent: [{exercise, load_kg, form_score, flags: [codes], pain: bool}] newest first."""
    last_loads: dict[str, float] = {}
    top_cues: dict[str, str] = {}
    for r in recent:
        last_loads.setdefault(r["exercise"], float(r.get("load_kg") or 0))
        if r["exercise"] not in top_cues and r.get("flags"):
            top_cues[r["exercise"]] = CUE_LIBRARY.get(r["flags"][0], ("Controlled reps with full range.",))[0]
    pain = any(r.get("pain") for r in recent[:3])
    conservative = conservative or pain
    cap = 0.0 if conservative else 5.0
    payload = {"client": profile_for_llm(profile), "recent_sessions": recent[:8],
               "recent_exercises": list(dict.fromkeys(r["exercise"] for r in recent)),
               "top_cues": top_cues, "conservative_mode": conservative,
               "max_load_increase_pct": cap, "safety_reasons": reasons}

    def validate(p: WeekPlan) -> list[str]:
        problems = []
        if not p.sessions:
            problems.append("The plan has no sessions.")
        if BANNED.search(" ".join([p.focus, p.progression_rule, *[s.cue for s in p.sessions]])):
            problems.append("Do not mention diet, calories or weight loss.")
        return problems

    plan, source, warnings = await _generate(llm, prompts.SYSTEM_PROMPT, prompts.plan_prompt(payload), WeekPlan,
                                             validate, lambda: fallback_plan(payload))
    plan, notes = clamp_plan(plan, last_loads, cap, profile.get("training_days_per_week", 3))
    review = list(plan.coach_review_points)
    if pain:
        review.insert(0, "The client reported pain in a recent set. Check in before approving any training.")
    for r in reasons:
        if r not in review:
            review.append(r)
    plan.coach_review_points = review
    return {"draft": plan.model_dump(), "source": source, "warnings": warnings + notes,
            "max_load_increase_pct": cap, "conservative_mode": conservative}
