"""Prompts for the three Gemma tasks. The model only ever sees NUMBERS and TEXT, never video or images."""
from __future__ import annotations

import json

SAFETY_RULES = """\
SAFETY RULES (always follow):
- You are a coaching helper, NOT a medical tool. Never diagnose an injury or condition.
- Never give diet, calorie, nutrition or weight-loss numbers or advice. Training feedback only.
- If pain was reported, the client is 65 or older, or injuries are listed: be conservative, never suggest adding load,
  and tell the client to check with their coach.
- If pain was reported, the client message must tell the client to stop the exercise and talk to their coach.
- Your text is a DRAFT. A human coach will review it before the client sees it.
"""

NUMBER_RULES = """\
NUMBER RULES:
- You may only explain the numbers you are given. Do NOT invent, estimate or calculate any new measurement.
- Only write a number if it appears in the data (for example an angle, a rep number, a percentage or a score).
- Prefer words over numbers when unsure.
"""

SYSTEM_PROMPT = (
    "You are RepCheck's writing assistant for an online personal trainer. "
    "Measurements were already taken by software and judged by fixed rules; you explain them in clear, kind, "
    "plain English.\n\n" + SAFETY_RULES + "\n" + NUMBER_RULES +
    "\nAlways reply with JSON that matches the requested schema and nothing else."
)


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=1, default=str, ensure_ascii=False)


def feedback_prompt(payload: dict) -> str:
    j = payload["judgement"]
    return f"""TASK: Write feedback for ONE workout video.

DATA (JSON):
{_dump(payload)}

REQUIREMENTS:
- "summary": 1-2 sentences for the coach.
- "what_went_well": 1-3 short items, based only on things that are NOT in judgement.flags.
- "fix_next_time": at most {j.get('cue_limit', 3)} items, most important first. Each has a short cue (what to do),
  why (one sentence), and reps (rep numbers from the flag, if any). Base them only on judgement.flags.
- "coach_only_notes": things the coach should know (safety reasons, fatigue, data quality, limb-ratio notes).
- "client_message": friendly, simple English, MAX 120 words, at most {j.get('cue_limit', 3)} cues.
  Address the client as "you". Do not use the client's name.
- If judgement.safety.pain_reported is true: do NOT suggest adding load; the message must tell the client to stop and
  talk to their coach.
- If judgement.safety.conservative_mode is true: be careful and say the coach will check before any load change.
"""


def progress_prompt(payload: dict) -> str:
    return f"""TASK: Summarise the client's progress over their recent sessions.

DATA (JSON):
{_dump(payload)}

REQUIREMENTS:
- "trend": use data.history.trend exactly.
- "highlights": 1-3 positive facts from the data. "concerns": 0-3 careful, factual concerns.
- "client_message": friendly, simple English, MAX 120 words. If history.trend is "not_enough_data", say a few more
  sessions are needed to see a pattern.
- Never suggest adding load if safety.conservative_mode is true.
"""


def plan_prompt(payload: dict) -> str:
    return f"""TASK: Suggest next week's training plan as a DRAFT for the coach to review.

DATA (JSON):
{_dump(payload)}

REQUIREMENTS:
- Use only these exercises: squat, pushup, bicep_curl. Respect the client's equipment and injuries.
- Use at most data.client.training_days_per_week sessions; "day" is 1 (Monday) to 7 (Sunday).
- "reps" is a short range like "8-10". "tempo" is like "3-1-1".
- "load_change_pct": change vs the last session load for that exercise, as a percentage. It must NOT be higher than
  data.max_load_increase_pct. Use 0 or a negative number when unsure.
- "load_suggestion" is a short human sentence about load (the software will rewrite exact numbers).
- "cue": one short technique cue from the recent flags.
- "coach_review_points": what the coach should check before approving (always include anything about pain, age,
  injuries or poor video quality).
- If data.conservative_mode is true, keep volume and load the same or lower, and add a review point.
"""


def retry_suffix(problems: list[str]) -> str:
    return ("\n\nYour previous answer had problems:\n- " + "\n- ".join(problems) +
            "\nFix them and answer again with JSON only.")
