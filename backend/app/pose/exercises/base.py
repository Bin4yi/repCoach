"""Exercise analyzer interface + shared helpers (rep detection, flags, balance)."""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import find_peaks

from ..types import PoseSequence

# A flag is only raised if at least this share of reps show the problem (and at least one rep does).
MIN_FLAG_FRACTION = 0.25
# Share of a rep's range counted as "at the top" when finding rep start/end.
TOP_BAND = 0.10


@dataclass
class AnalysisContext:
    """Facts about the client that make rules fairer (never used to diagnose anything)."""
    experience_level: str = "intermediate"  # beginner | intermediate | advanced


@dataclass
class Rep:
    index: int          # 1-based
    start: int          # frame where the descent/flexion begins
    bottom: int         # frame of the extreme (lowest angle)
    end: int            # frame where the rep is finished
    top_before: float   # signal value at the top before the rep
    top_after: float    # signal value at the top after the rep


@dataclass
class ExerciseResult:
    exercise: str
    view: str
    side: str
    signal_name: str
    reps: list[dict] = field(default_factory=list)     # per-rep metrics
    flags: list[dict] = field(default_factory=list)
    balance: dict | None = None
    extras: dict = field(default_factory=dict)         # limb ratios, config used, etc.
    signal: list[float] = field(default_factory=list)  # main signal (for charts / debugging)

    def to_dict(self) -> dict:
        return {
            "exercise": self.exercise, "view": self.view, "side": self.side,
            "signal_name": self.signal_name, "reps": self.reps, "flags": self.flags,
            "balance": self.balance, "extras": self.extras,
        }


def fill_nan(sig: np.ndarray) -> np.ndarray:
    """Linearly fill NaNs; all-NaN stays NaN."""
    sig = np.asarray(sig, dtype=float).copy()
    bad = np.isnan(sig)
    if bad.all():
        return sig
    if bad.any():
        idx = np.arange(len(sig))
        sig[bad] = np.interp(idx[bad], idx[~bad], sig[~bad])
    return sig


def detect_reps(sig: np.ndarray, fps: float, min_prominence: float, min_rep_seconds: float) -> list[Rep]:
    """Find reps as valleys of a signal where HIGH means 'extended / at the top'.

    Rep start/end are the last/first frames where the signal is within TOP_BAND of the top level.
    """
    sig = fill_nan(sig)
    if len(sig) < 5 or np.isnan(sig).all():
        return []
    valleys, _ = find_peaks(-sig, prominence=min_prominence, distance=max(1, int(min_rep_seconds * fps)))
    reps: list[Rep] = []
    for k, b in enumerate(valleys):
        prev_b = valleys[k - 1] if k > 0 else 0
        next_b = valleys[k + 1] if k + 1 < len(valleys) else len(sig) - 1
        bottom_val = sig[b]

        seg_before = sig[prev_b:b + 1]
        top_before = float(np.max(seg_before))
        thr = top_before - TOP_BAND * (top_before - bottom_val)
        start = prev_b + int(np.max(np.nonzero(seg_before >= thr)[0]))

        seg_after = sig[b:next_b + 1]
        top_after = float(np.max(seg_after))
        thr2 = top_after - TOP_BAND * (top_after - bottom_val)
        end = b + int(np.min(np.nonzero(seg_after >= thr2)[0]))
        reps.append(Rep(index=k + 1, start=start, bottom=int(b), end=end,
                        top_before=top_before, top_after=top_after))
    return reps


def common_rep_metrics(sig: np.ndarray, rep: Rep, fps: float) -> dict:
    """Metrics every exercise shares: timing, range of motion, concentric speed."""
    sig = fill_nan(sig)
    bottom_val = float(sig[rep.bottom])
    ecc = max((rep.bottom - rep.start) / fps, 1e-3)
    con = max((rep.end - rep.bottom) / fps, 1e-3)
    top = max(rep.top_before, rep.top_after)
    rom = top - bottom_val
    # time spent within 2% of the range around the bottom (a natural turnaround is ~0.2-0.3 s)
    band = bottom_val + 0.02 * rom
    dwell = float(np.sum(sig[rep.start:rep.end + 1] <= band)) / fps
    return {
        "rep": rep.index,
        "start_frame": rep.start, "bottom_frame": rep.bottom, "end_frame": rep.end,
        "depth_angle": round(bottom_val, 1),
        "range_of_motion": round(rom, 1),
        "eccentric_s": round(ecc, 2),
        "concentric_s": round(con, 2),
        "bottom_pause_s": round(dwell, 2),
        # mean concentric speed in signal-units per second (deg/s for angle signals)
        "concentric_velocity": round(float(sig[rep.end] - bottom_val) / con, 1),
        "top_value": round(top, 1),
    }


def severity_from_fraction(frac: float) -> str:
    return "high" if frac >= 0.7 else "medium" if frac >= 0.3 else "low"


def make_flag(code: str, reps: list[int], n_reps: int, evidence: str, severity: str | None = None) -> dict:
    frac = len(reps) / max(n_reps, 1)
    return {"code": code, "severity": severity or severity_from_fraction(frac), "reps": sorted(reps),
            "fraction": round(frac, 2), "evidence": evidence}


def flag_if_enough(code: str, reps: list[int], n_reps: int, evidence: str) -> dict | None:
    if reps and len(reps) / max(n_reps, 1) >= MIN_FLAG_FRACTION:
        return make_flag(code, reps, n_reps, evidence)
    return None


def limb_ratio(seq: PoseSequence, side: str) -> float | None:
    """Femur length / torso length (a body-proportion fact, used to avoid unfair squat-lean cues)."""
    hip, knee, sh = seq.joint(side, "hip"), seq.joint(side, "knee"), seq.joint(side, "shoulder")
    femur = np.linalg.norm((hip - knee)[:, :2], axis=-1)
    torso = np.linalg.norm((sh - hip)[:, :2], axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = femur / torso
    if np.all(np.isnan(r)):
        return None
    return float(np.nanmedian(r))


def side_balance(left: np.ndarray, right: np.ndarray, reps: list[Rep], visible: bool) -> dict | None:
    """Compare the deepest angle on the left and right side per rep (only if both sides are visible)."""
    if not visible or not reps:
        return None
    l, r = fill_nan(left), fill_nan(right)
    if np.isnan(l).all() or np.isnan(r).all():
        return None
    lm = [float(np.min(l[x.start:x.end + 1])) for x in reps]
    rm = [float(np.min(r[x.start:x.end + 1])) for x in reps]
    diff = float(np.mean(np.abs(np.array(lm) - np.array(rm))))
    base = float(np.mean(lm + rm)) or 1.0
    return {"left_mean_min_deg": round(float(np.mean(lm)), 1), "right_mean_min_deg": round(float(np.mean(rm)), 1),
            "diff_deg": round(diff, 1), "diff_pct": round(100 * diff / base, 1)}


def both_sides_visible(seq: PoseSequence, names: list[str], min_vis: float = 0.6) -> bool:
    from ..types import SIDES
    for s in ("L", "R"):
        if float(np.mean(seq.vis[:, [SIDES[s][n] for n in names]])) < min_vis:
            return False
    return True


class ExerciseAnalyzer(ABC):
    """Turns a (smoothed) PoseSequence into per-rep metrics and flags."""
    name: str

    @abstractmethod
    def analyze(self, seq: PoseSequence, view: str, ctx: AnalysisContext | None = None) -> ExerciseResult:
        ...


def nanmax_or(arr: np.ndarray, default: float = float("nan")) -> float:
    return float(np.nanmax(arr)) if arr.size and not np.all(np.isnan(arr)) else default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def is_finite(x) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))
