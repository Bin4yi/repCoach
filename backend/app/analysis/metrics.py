"""Set-level metrics and the 0-100 form score. All computed in code, never by the LLM."""
from __future__ import annotations

import numpy as np

from ..pose.exercises.base import ExerciseResult

# Maximum points a flag can cost when it affects EVERY rep (scaled by the share of reps affected).
# Documented in DECISIONS.md.
FLAG_WEIGHTS = {
    "shallow_depth": 20,
    "excess_forward_lean": 15,
    "knee_cave": 20,
    "depth_drops_with_fatigue": 10,
    "rushed_eccentric": 8,
    "partial_range": 20,
    "hip_sag": 15,
    "hips_high": 10,
    "no_lockout": 10,
    "elbow_drift": 12,
    "body_swing": 15,
}
SEVERITY_MULT = {"low": 0.6, "medium": 0.85, "high": 1.0}
CONSISTENCY_MAX_PENALTY = 8.0   # tempo that varies a lot from rep to rep costs up to this many points
CONSISTENCY_CV_FULL = 0.5       # coefficient of variation at which the full penalty applies
ASYMMETRY_MAX_PENALTY = 6.0     # left/right difference costs up to this many points
ASYMMETRY_PCT_FULL = 15.0       # % difference at which the full penalty applies


def velocity_loss_pct(reps: list[dict]) -> float | None:
    """How much slower the last reps' lifting phase is vs the first reps (fatigue signal). Needs 4+ reps."""
    n = len(reps)
    if n < 4:
        return None
    k = 2 if n < 8 else max(2, n // 4)
    first = np.mean([r["concentric_velocity"] for r in reps[:k]])
    last = np.mean([r["concentric_velocity"] for r in reps[-k:]])
    if first <= 0:
        return None
    return round(float(max(0.0, (first - last) / first * 100)), 1)


def form_score(flags: list[dict], reps: list[dict], balance: dict | None) -> int | None:
    """100 minus weighted penalties. See FLAG_WEIGHTS; consistency and asymmetry add small penalties."""
    if not reps:
        return None
    penalty = 0.0
    for f in flags:
        w = FLAG_WEIGHTS.get(f["code"], 10)
        penalty += w * (0.4 + 0.6 * f.get("fraction", 1.0)) * SEVERITY_MULT.get(f["severity"], 1.0)
    if len(reps) >= 3:
        durations = np.array([r["eccentric_s"] + r["concentric_s"] for r in reps])
        cv = float(np.std(durations) / np.mean(durations))
        penalty += CONSISTENCY_MAX_PENALTY * min(1.0, cv / CONSISTENCY_CV_FULL)
    if balance:
        penalty += ASYMMETRY_MAX_PENALTY * min(1.0, balance["diff_pct"] / ASYMMETRY_PCT_FULL)
    return int(round(max(0.0, min(100.0, 100.0 - penalty))))


def set_metrics(result: ExerciseResult) -> dict:
    """Summary numbers for the whole set."""
    reps = result.reps
    n = len(reps)
    out: dict = {"rep_count": n}
    if n == 0:
        out.update(form_score=None, depth_mean=None, depth_std=None, tempo_cv=None,
                   velocity_loss_pct=None, balance=None, avg_eccentric_s=None, avg_concentric_s=None)
        return out
    depths = [r["depth_angle"] for r in reps if r.get("depth_angle") is not None]
    dur = np.array([r["eccentric_s"] + r["concentric_s"] for r in reps])
    out.update(
        depth_mean=round(float(np.mean(depths)), 1) if depths else None,
        depth_std=round(float(np.std(depths)), 1) if depths else None,
        depth_best=round(float(np.min(depths)), 1) if depths else None,
        avg_eccentric_s=round(float(np.mean([r["eccentric_s"] for r in reps])), 2),
        avg_concentric_s=round(float(np.mean([r["concentric_s"] for r in reps])), 2),
        tempo_cv=round(float(np.std(dur) / np.mean(dur)), 2) if n >= 2 else 0.0,
        velocity_loss_pct=velocity_loss_pct(reps),
        balance=result.balance,
        form_score=form_score(result.flags, reps, result.balance),
    )
    return out
