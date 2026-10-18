"""Push-up analyzer (side view): elbow depth, lockout, body line."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..angles import angle
from ..types import PoseSequence
from .base import (AnalysisContext, ExerciseAnalyzer, ExerciseResult, both_sides_visible, common_rep_metrics,
                   detect_reps, fill_nan, flag_if_enough, side_balance)


@dataclass(frozen=True)
class PushupConfig:
    """All push-up thresholds in one place. Angles in degrees."""
    min_prominence_deg: float = 30.0   # elbow angle change needed to count a rep
    min_rep_seconds: float = 0.8
    depth_target_deg: float = 100.0    # elbow angle at the bottom should be BELOW this (about 90 deg)
    beginner_depth_slack_deg: float = 10.0
    lockout_min_deg: float = 160.0     # elbows should reach at least this at the top
    body_line_min_deg: float = 165.0   # shoulder-hip-ankle angle below this = hips sag or pike
    no_lockout_fraction: float = 0.5   # flag if this share of reps never lock out


CFG = PushupConfig()


class PushupAnalyzer(ExerciseAnalyzer):
    name = "pushup"

    def __init__(self, cfg: PushupConfig = CFG):
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

        sh, hip, an = seq.joint(side, "shoulder"), seq.joint(side, "hip"), seq.joint(side, "ankle")
        body = fill_nan(angle(sh, hip, an))
        # signed hip offset from the shoulder-ankle line: > 0 means the hip is BELOW the line (sag)
        with np.errstate(invalid="ignore", divide="ignore"):
            line_y = sh[:, 1] + (hip[:, 0] - sh[:, 0]) * (an[:, 1] - sh[:, 1]) / (an[:, 0] - sh[:, 0])
        hip_off = fill_nan(hip[:, 1] - line_y)

        target = c.depth_target_deg + (c.beginner_depth_slack_deg if ctx.experience_level == "beginner" else 0)
        res = ExerciseResult(exercise="pushup", view=view, side=side, signal_name="elbow_angle_deg",
                             signal=[round(float(x), 1) for x in elbow])
        partial, sag, high, no_lock = [], [], [], []
        for r in reps:
            m = common_rep_metrics(elbow, r, seq.fps)
            w = slice(r.start, r.end + 1)
            m["lockout_angle"] = round(max(r.top_before, r.top_after), 1)
            m["body_line_deg"] = round(float(np.nanmin(body[w])), 1)
            mid = r.bottom
            m["hip_position"] = "sag" if hip_off[mid] > 0 else "high"
            res.reps.append(m)
            if m["depth_angle"] > target:
                partial.append(r.index)
            if m["body_line_deg"] < c.body_line_min_deg:
                (sag if hip_off[mid] > 0 else high).append(r.index)
            if m["lockout_angle"] < c.lockout_min_deg:
                no_lock.append(r.index)

        n = len(reps)
        by = lambda key: {x["rep"]: x[key] for x in res.reps}  # noqa: E731
        d, b, lo = by("depth_angle"), by("body_line_deg"), by("lockout_angle")
        flags = [
            flag_if_enough("partial_range", partial, n,
                           f"min elbow angle {np.mean([d[i] for i in partial]):.0f}° vs target < {target:.0f}°") if partial else None,
            flag_if_enough("hip_sag", sag, n,
                           f"body line {np.mean([b[i] for i in sag]):.0f}° vs at least {c.body_line_min_deg:.0f}° (hips dropping)") if sag else None,
            flag_if_enough("hips_high", high, n,
                           f"body line {np.mean([b[i] for i in high]):.0f}° vs at least {c.body_line_min_deg:.0f}° (hips too high)") if high else None,
        ]
        if no_lock and len(no_lock) / max(n, 1) >= c.no_lockout_fraction:
            flags.append(flag_if_enough("no_lockout", no_lock, n,
                                        f"elbows reached only {np.mean([lo[i] for i in no_lock]):.0f}° at the top vs {c.lockout_min_deg:.0f}°"))
        res.flags = [f for f in flags if f]
        res.balance = side_balance(self._elbow(seq, "L"), self._elbow(seq, "R"), reps,
                                   both_sides_visible(seq, ["shoulder", "elbow", "wrist"]))
        res.extras = {"depth_target_deg": target}
        return res
