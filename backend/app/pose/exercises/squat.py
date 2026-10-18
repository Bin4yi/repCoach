"""Squat analyzer (side view: depth, lean, knee travel, tempo; front view: knee cave)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..angles import angle, torso_angle_from_vertical
from ..types import PoseSequence
from .base import (AnalysisContext, ExerciseAnalyzer, ExerciseResult, Rep, both_sides_visible, clamp,
                   common_rep_metrics, detect_reps, fill_nan, flag_if_enough, limb_ratio, make_flag,
                   side_balance)


@dataclass(frozen=True)
class SquatConfig:
    """All squat thresholds in one place. Angles in degrees."""
    # --- rep detection ---
    min_prominence_deg: float = 25.0    # knee angle must change this much to count as a rep (ignores wobble)
    min_prominence_rel: float = 0.08    # same, for the front-view hip-height signal (0..1 scale)
    min_rep_seconds: float = 1.0        # two reps cannot be closer than this
    # --- depth ---
    depth_target_deg: float = 95.0      # knee angle at the bottom should be BELOW this (about parallel)
    beginner_depth_slack_deg: float = 10.0  # beginners get a more forgiving target
    # --- forward lean ---
    lean_limit_deg: float = 45.0        # torso lean from vertical above this is flagged...
    lean_ratio_ref: float = 0.90        # ...adjusted for femur/torso ratio: longer femur => more lean is normal
    lean_ratio_gain_deg: float = 60.0   # extra allowed degrees per +1.0 of femur/torso ratio above the reference
    lean_adjust_max_deg: float = 10.0   # never adjust by more than this either way
    # --- tempo ---
    min_eccentric_s: float = 1.0        # going down faster than this is "rushed"
    beginner_min_eccentric_s: float = 0.8
    # --- knee cave (front view) ---
    valgus_ratio_limit: float = 0.12    # knee drifts inward by more than 12% of hip width
    # --- fatigue ---
    fatigue_depth_drop_deg: float = 8.0  # last third of reps this much shallower than the first third
    fatigue_min_reps: int = 4


CFG = SquatConfig()


class SquatAnalyzer(ExerciseAnalyzer):
    name = "squat"

    def __init__(self, cfg: SquatConfig = CFG):
        self.cfg = cfg

    # ------------------------------------------------------------------ helpers
    def _knee_angle(self, seq: PoseSequence, side: str) -> np.ndarray:
        return angle(seq.joint(side, "hip"), seq.joint(side, "knee"), seq.joint(side, "ankle"))

    def lean_limit(self, ratio: float | None) -> float:
        c = self.cfg
        if ratio is None:
            return c.lean_limit_deg
        adj = clamp(c.lean_ratio_gain_deg * (ratio - c.lean_ratio_ref), -c.lean_adjust_max_deg, c.lean_adjust_max_deg)
        return c.lean_limit_deg + adj

    # ------------------------------------------------------------------ main
    def analyze(self, seq: PoseSequence, view: str, ctx: AnalysisContext | None = None) -> ExerciseResult:
        ctx = ctx or AnalysisContext()
        if view == "front":
            return self._analyze_front(seq, ctx)
        return self._analyze_side(seq, ctx)

    def _analyze_side(self, seq: PoseSequence, ctx: AnalysisContext) -> ExerciseResult:
        c = self.cfg
        side = seq.near_side()
        knee = fill_nan(self._knee_angle(seq, side))
        reps = detect_reps(knee, seq.fps, c.min_prominence_deg, c.min_rep_seconds)

        sh, hip, kn, an = (seq.joint(side, n) for n in ("shoulder", "hip", "knee", "ankle"))
        toe = seq.joint(side, "toe")
        lean = fill_nan(torso_angle_from_vertical(sh, hip))
        face = seq.facing_sign(side)
        shin_len = np.linalg.norm((kn - an)[:, :2], axis=-1)
        # how far the knee is in front of the toe, as a share of shin length (positive = past the toes)
        travel = fill_nan(((kn[:, 0] - toe[:, 0]) * face) / shin_len)

        ratio = limb_ratio(seq, side)
        lean_limit = self.lean_limit(ratio)
        depth_target = c.depth_target_deg + (c.beginner_depth_slack_deg if ctx.experience_level == "beginner" else 0)
        min_ecc = c.beginner_min_eccentric_s if ctx.experience_level == "beginner" else c.min_eccentric_s

        res = ExerciseResult(exercise="squat", view="side", side=side, signal_name="knee_angle_deg",
                             signal=[round(float(x), 1) for x in knee])
        shallow, leaning, rushed = [], [], []
        for r in reps:
            m = common_rep_metrics(knee, r, seq.fps)
            w = slice(r.start, r.end + 1)
            m["hip_below_knee"] = bool(hip[r.bottom, 1] > kn[r.bottom, 1])
            m["max_torso_lean_deg"] = round(float(np.nanmax(lean[w])), 1)
            m["knee_travel_past_toe"] = round(float(np.nanmax(travel[w])), 2)
            res.reps.append(m)
            if m["depth_angle"] > depth_target:
                shallow.append(r.index)
            if m["max_torso_lean_deg"] > lean_limit:
                leaning.append(r.index)
            if m["eccentric_s"] < min_ecc:
                rushed.append(r.index)

        n = len(reps)
        depths = {x["rep"]: x["depth_angle"] for x in res.reps}
        leans = {x["rep"]: x["max_torso_lean_deg"] for x in res.reps}
        ecc = {x["rep"]: x["eccentric_s"] for x in res.reps}
        flags = [
            flag_if_enough("shallow_depth", shallow, n,
                           f"min knee angle {np.mean([depths[i] for i in shallow]):.0f}° vs target < {depth_target:.0f}°") if shallow else None,
            flag_if_enough("excess_forward_lean", leaning, n,
                           f"max torso lean {np.mean([leans[i] for i in leaning]):.0f}° vs limit {lean_limit:.0f}°"
                           + (f" (adjusted for femur/torso ratio {ratio:.2f})" if ratio else "")) if leaning else None,
            flag_if_enough("rushed_eccentric", rushed, n,
                           f"descent took {np.mean([ecc[i] for i in rushed]):.1f}s vs at least {min_ecc:.1f}s") if rushed else None,
        ]
        # fatigue: do the last reps get shallower than the first ones?
        if n >= c.fatigue_min_reps:
            k = max(1, n // 3)
            first, last = np.mean([x["depth_angle"] for x in res.reps[:k]]), np.mean([x["depth_angle"] for x in res.reps[-k:]])
            if last - first > c.fatigue_depth_drop_deg:
                flags.append(make_flag("depth_drops_with_fatigue", [x["rep"] for x in res.reps[-k:]], n,
                                       f"knee angle at the bottom went from {first:.0f}° to {last:.0f}° "
                                       f"(first {k} reps vs last {k})", severity="medium"))
        res.flags = [f for f in flags if f]

        near_names = ["hip", "knee", "ankle"]
        res.balance = side_balance(self._knee_angle(seq, "L"), self._knee_angle(seq, "R"), reps,
                                   both_sides_visible(seq, near_names))
        res.extras = {"femur_torso_ratio": round(ratio, 2) if ratio else None,
                      "lean_limit_deg": round(lean_limit, 1), "depth_target_deg": depth_target,
                      "min_eccentric_s": min_ecc, "facing": "right" if face > 0 else "left"}
        return res

    def _analyze_front(self, seq: PoseSequence, ctx: AnalysisContext) -> ExerciseResult:
        """Front view cannot measure knee angle well; track hip height (rel.) and knee cave."""
        c = self.cfg
        pts = seq.pts
        hip_y = (pts[:, 23, 1] + pts[:, 24, 1]) / 2
        ank_y = (pts[:, 27, 1] + pts[:, 28, 1]) / 2
        height = fill_nan(ank_y - hip_y)
        ref = np.nanpercentile(height, 95) if not np.all(np.isnan(height)) else 1.0
        sig = fill_nan(height / ref)  # ~1.0 standing, lower when squatting
        reps = detect_reps(sig, seq.fps, c.min_prominence_rel, c.min_rep_seconds)

        hip_w = np.abs(pts[:, 23, 0] - pts[:, 24, 0])
        mid_x = (pts[:, 23, 0] + pts[:, 24, 0]) / 2
        valgus = np.zeros((len(sig), 2))
        for j, (h, k, a) in enumerate(((23, 25, 27), (24, 26, 28))):
            hx, kx, ax = pts[:, h, 0], pts[:, k, 0], pts[:, a, 0]
            hy, ky, ay = pts[:, h, 1], pts[:, k, 1], pts[:, a, 1]
            with np.errstate(invalid="ignore", divide="ignore"):
                frac = (ky - hy) / (ay - hy)
                expected = hx + (ax - hx) * frac          # where the knee sits if hip-knee-ankle were straight
                out_sign = np.sign(hx - mid_x)            # outward direction for this leg
                valgus[:, j] = ((expected - kx) * out_sign) / hip_w
        valgus = np.apply_along_axis(fill_nan, 0, valgus)

        res = ExerciseResult(exercise="squat", view="front", side="both", signal_name="hip_height_rel",
                             signal=[round(float(x), 3) for x in sig])
        cave = []
        for r in reps:
            m = common_rep_metrics(sig, r, seq.fps)
            w = slice(r.start, r.end + 1)
            m["depth_angle"] = None  # not measurable from the front
            m["hip_drop_pct"] = round(100 * (1 - float(sig[r.bottom])), 1)
            m["knee_valgus_ratio"] = round(float(np.nanmax(valgus[w])), 3)
            res.reps.append(m)
            if m["knee_valgus_ratio"] > c.valgus_ratio_limit:
                cave.append(r.index)
        n = len(reps)
        vals = {x["rep"]: x["knee_valgus_ratio"] for x in res.reps}
        f = flag_if_enough("knee_cave", cave, n,
                           f"knees moved inward by {100 * np.mean([vals[i] for i in cave]):.0f}% of hip width "
                           f"(limit {100 * c.valgus_ratio_limit:.0f}%)") if cave else None
        res.flags = [f] if f else []
        res.extras = {"note": "Front view: depth angle is not measured; use side view for depth."}
        return res
