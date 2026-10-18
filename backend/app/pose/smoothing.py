"""Clean up jittery / missing landmarks before measuring anything."""
from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter

VIS_MIN = 0.5       # below this a landmark is treated as missing
MAX_GAP = 5         # fill gaps of up to this many frames by interpolation
SG_WINDOW_S = 0.25  # Savitzky-Golay window in seconds (forced odd, min 5 frames)
SG_ORDER = 2


def _interp_gaps(series: np.ndarray, valid: np.ndarray, max_gap: int) -> np.ndarray:
    """Linear interpolation across invalid runs no longer than `max_gap`; longer runs stay NaN."""
    out = series.astype(float).copy()
    out[~valid] = np.nan
    n = len(out)
    i = 0
    while i < n:
        if valid[i]:
            i += 1
            continue
        j = i
        while j < n and not valid[j]:
            j += 1
        # invalid run is [i, j)
        if i > 0 and j < n and (j - i) <= max_gap:
            out[i:j] = np.linspace(out[i - 1], out[j], j - i + 2)[1:-1]
        i = j
    return out


def _savgol_nan(s: np.ndarray, win: int) -> np.ndarray:
    """Savitzky-Golay on each NaN-free run (runs too short for the window are left as-is)."""
    out = s.copy()
    ok = ~np.isnan(s)
    n = len(s)
    i = 0
    while i < n:
        if not ok[i]:
            i += 1
            continue
        j = i
        while j < n and ok[j]:
            j += 1
        seg = j - i
        w = win if win <= seg else (seg if seg % 2 == 1 else seg - 1)
        if w >= 5 and w > SG_ORDER:
            out[i:j] = savgol_filter(s[i:j], w, SG_ORDER)
        i = j
    return out


def smooth_array(pts: np.ndarray, vis: np.ndarray, fps: float, vis_min: float = VIS_MIN,
                 max_gap: int = MAX_GAP) -> np.ndarray:
    """Drop low-visibility points, fill short gaps, Savitzky-Golay smooth.

    pts: (T, 33, D), vis: (T, 33). Returns the same shape; long gaps remain NaN
    (quality.py reports them and analyzers skip NaN frames).
    """
    _, n_lm, d = pts.shape
    out = np.full(pts.shape, np.nan, dtype=float)
    win = max(5, int(round(SG_WINDOW_S * fps)) | 1)
    for k in range(n_lm):
        valid = vis[:, k] >= vis_min
        if valid.all() and not np.isnan(pts[:, k]).any() and len(pts) >= win:
            out[:, k, :] = savgol_filter(pts[:, k, :], win, SG_ORDER, axis=0)  # fast path: nothing missing
            continue
        for c in range(d):
            out[:, k, c] = _savgol_nan(_interp_gaps(pts[:, k, c], valid, max_gap), win)
    return out


def smooth_sequence(seq):
    """Return a new PoseSequence with smoothed img/world coordinates."""
    from .types import PoseSequence

    img = smooth_array(seq.img, seq.vis, seq.fps)
    world = smooth_array(seq.world, seq.vis, seq.fps) if seq.world is not None else None
    return PoseSequence(img=img, vis=seq.vis, fps=seq.fps, world=world, detected=seq.detected,
                        multi_person=seq.multi_person, frame_size=seq.frame_size, meta=dict(seq.meta))
