"""Is this video good enough to measure? Friendly reasons if not."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .types import L_SHOULDER, R_SHOULDER, SIDES, PoseSequence

FULL_BODY_MIN_PCT = 0.60       # share of frames with the needed body parts visible
DETECTED_MIN_PCT = 0.60        # share of frames where a person was found at all
MULTI_PERSON_MAX_PCT = 0.30    # share of frames allowed to contain a 2nd person
VIS_OK = 0.5                   # landmark counts as visible above this
# shoulder-width / torso-length in the image: small = side view, large = front view
VIEW_SPLIT_RATIO = 0.45

REQUIRED = {
    "squat": ["shoulder", "hip", "knee", "ankle"],
    "pushup": ["shoulder", "elbow", "wrist", "hip", "ankle"],
    "bicep_curl": ["shoulder", "elbow", "wrist", "hip"],
}


@dataclass
class QualityReport:
    ok: bool
    needs_reshoot: bool
    reason: str | None
    full_body_pct: float
    detected_pct: float
    avg_visibility: float
    multi_person_pct: float
    view_estimate: str            # "side" | "front" | "unknown"
    view_matches: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_view(seq: PoseSequence) -> tuple[str, float]:
    """Compare shoulder width to torso length in the image plane (not world coords)."""
    side = seq.near_side()
    sh = seq.img[:, SIDES[side]["shoulder"], :2]
    hp = seq.img[:, SIDES[side]["hip"], :2]
    width = np.abs(seq.img[:, L_SHOULDER, 0] - seq.img[:, R_SHOULDER, 0])
    torso = np.linalg.norm(sh - hp, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = width / torso
    if np.all(np.isnan(ratio)):
        return "unknown", float("nan")
    r = float(np.nanmedian(ratio))
    return ("side" if r < VIEW_SPLIT_RATIO else "front"), r


def assess_quality(seq: PoseSequence, exercise: str, camera_view: str) -> QualityReport:
    """Build the quality report. Call on the RAW (unsmoothed) sequence so visibility is honest."""
    n = max(seq.n_frames, 1)
    detected_pct = float(np.mean(seq.detected)) if seq.n_frames else 0.0
    multi_pct = float(np.mean(seq.multi_person)) if seq.n_frames else 0.0

    need = REQUIRED[exercise]
    full = np.zeros(seq.n_frames, dtype=bool)
    for idx in SIDES.values():
        ids = [idx[k] for k in need]
        full |= np.all(seq.vis[:, ids] >= VIS_OK, axis=1)
    full &= seq.detected
    full_pct = float(np.sum(full)) / n

    side = seq.near_side()
    avg_vis = float(np.mean(seq.vis[:, [SIDES[side][k] for k in need]])) if seq.n_frames else 0.0

    view_est, _ = estimate_view(seq)
    view_matches = view_est in ("unknown", camera_view)

    notes: list[str] = []
    reason: str | None = None
    if seq.n_frames < seq.fps * 2 or detected_pct < DETECTED_MIN_PCT:
        reason = "We could not see you clearly. Please film again in good light with your whole body in view."
    elif full_pct < FULL_BODY_MIN_PCT:
        reason = (f"Please film from the {camera_view} with your whole body in view.")
    elif multi_pct > MULTI_PERSON_MAX_PCT:
        reason = "More than one person is in the video. Please film again with only you in view."
    elif not view_matches:
        reason = (f"The camera looks like a {view_est} view, but you chose {camera_view}. "
                  f"Please film from the {camera_view}, or change the camera view setting.")
    if reason is None and avg_vis < 0.7:
        notes.append("Some body parts were hard to see; results may be less exact.")
    if 0 < multi_pct <= MULTI_PERSON_MAX_PCT:
        notes.append("Another person was briefly in view.")

    needs = reason is not None
    return QualityReport(ok=not needs, needs_reshoot=needs, reason=reason, full_body_pct=round(full_pct, 3),
                         detected_pct=round(detected_pct, 3), avg_visibility=round(avg_vis, 3),
                         multi_person_pct=round(multi_pct, 3), view_estimate=view_est,
                         view_matches=view_matches, notes=notes)
