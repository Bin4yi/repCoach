"""Bicep curl analyzer (side view): range of motion, elbow drift, body swing."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..angles import angle, segment_angle_from_down, torso_angle_from_vertical
from ..types import PoseSequence
from .base import (AnalysisContext, ExerciseAnalyzer, ExerciseResult, both_sides_visible, common_rep_metrics,
                   detect_reps, fill_nan, flag_if_enough, side_balance)


@dataclass(frozen=True)
class CurlConfig:
    """All curl thresholds in one place. Angles in degrees."""
    min_prominence_deg: float = 40.0    # elbow angle change needed to count a rep
    min_rep_seconds: float = 1.0
    flexion_target_deg: float = 55.0    # elbow should bend to at least this angle at the top (smaller = more bend)
    extension_target_deg: float = 150.0  # elbow should straighten to at least this at the bottom
    beginner_slack_deg: float = 10.0
    drift_limit_deg: float = 20.0       # upper arm swinging forward more than this = elbow drift
    swing_limit_deg: float = 10.0       # torso lean changing by more than this within a rep = body swing


CFG = CurlConfig()


class BicepCurlAnalyzer(ExerciseAnalyzer):
    name = "bicep_curl"

    def __init__(self, cfg: CurlConfig = CFG):
        self.cfg = cfg

    @staticmethod
    def _elbow(seq: PoseSequence, side: str) -> np.ndarray:
        return angle(seq.joint(side, "shoulder"), seq.joint(side, "elbow"), seq.joint(side, "wrist"))

    def analyze(self, seq: PoseSequence, view: str, ctx: AnalysisContext | None = None) -> ExerciseResult:
        ctx = ctx or AnalysisContext()
        c = self.cfg
        side = seq.near_side()
        elbow = fill_nan(self._elbow(seq, side))
        reps = detect_reps(elbow, seq.fps, c.min_prominence_deg, c.min_rep_seconds)

        sh, el, hip = seq.joint(side, "shoulder"), seq.joint(side, "elbow"), seq.joint(side, "hip")
        arm_dev = fill_nan(segment_angle_from_down(sh, el))      # 0 = upper arm hanging straight down
        torso = fill_nan(torso_angle_from_vertical(sh, hip))

        slack = c.beginner_slack_deg if ctx.experience_level == "beginner" else 0
        flex_t, ext_t = c.flexion_target_deg + slack, c.extension_target_deg - slack
        res = ExerciseResult(exercise="bicep_curl", view=view, side=side, signal_name="elbow_angle_deg",
                             signal=[round(float(x), 1) for x in elbow])
        partial, drift, swing = [], [], []
        for r in reps:
            m = common_rep_metrics(elbow, r, seq.fps)
            w = slice(r.start, r.end + 1)
            m["extension_angle"] = m["top_value"]
            m["upper_arm_drift_deg"] = round(float(np.nanmax(arm_dev[w]) - np.nanmin(arm_dev[w])), 1)
            m["torso_swing_deg"] = round(float(np.nanmax(torso[w]) - np.nanmin(torso[w])), 1)
            res.reps.append(m)
            if m["depth_angle"] > flex_t or m["extension_angle"] < ext_t:
                partial.append(r.index)
            if m["upper_arm_drift_deg"] > c.drift_limit_deg:
                drift.append(r.index)
            if m["torso_swing_deg"] > c.swing_limit_deg:
                swing.append(r.index)

        n = len(reps)
        by = lambda key: {x["rep"]: x[key] for x in res.reps}  # noqa: E731
        fl, ex, dr, sw = by("depth_angle"), by("extension_angle"), by("upper_arm_drift_deg"), by("torso_swing_deg")
        flags = [
            flag_if_enough("partial_range", partial, n,
                           f"elbow bent to {np.mean([fl[i] for i in partial]):.0f}° (target < {flex_t:.0f}°) and "
                           f"straightened to {np.mean([ex[i] for i in partial]):.0f}° (target > {ext_t:.0f}°)") if partial else None,
            flag_if_enough("elbow_drift", drift, n,
                           f"upper arm moved {np.mean([dr[i] for i in drift]):.0f}° vs limit {c.drift_limit_deg:.0f}°") if drift else None,
            flag_if_enough("body_swing", swing, n,
                           f"torso moved {np.mean([sw[i] for i in swing]):.0f}° vs limit {c.swing_limit_deg:.0f}°") if swing else None,
        ]
        res.flags = [f for f in flags if f]
        res.balance = side_balance(self._elbow(seq, "L"), self._elbow(seq, "R"), reps,
                                   both_sides_visible(seq, ["shoulder", "elbow", "wrist"]))
        res.extras = {"flexion_target_deg": flex_t, "extension_target_deg": ext_t}
        return res
