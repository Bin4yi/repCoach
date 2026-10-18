"""Video/landmarks -> quality report + per-rep metrics + set metrics. No profile, no LLM."""
from __future__ import annotations

from pathlib import Path

from .analysis.metrics import set_metrics
from .pose.exercises import AnalysisContext, get_analyzer
from .pose.quality import assess_quality
from .pose.smoothing import smooth_sequence
from .pose.types import PoseSequence

NO_REPS_MESSAGE = ("We could not count any reps in this video. Please film the whole set, "
                   "with your whole body in view and good light.")


def analyze_sequence(seq: PoseSequence, exercise: str, view: str, experience_level: str = "intermediate") -> dict:
    """Run quality checks, smoothing and the exercise analyzer on raw landmarks."""
    quality = assess_quality(seq, exercise, view)
    out: dict = {"quality": quality.to_dict(), "reps": [], "flags": [], "set": None, "extras": {}, "side": None}
    if quality.needs_reshoot:
        return out

    smooth = smooth_sequence(seq)
    result = get_analyzer(exercise).analyze(smooth, view, AnalysisContext(experience_level))
    if not result.reps:
        out["quality"].update(ok=False, needs_reshoot=True, reason=NO_REPS_MESSAGE)
        return out

    flagged_by_rep: dict[int, list[str]] = {}
    for f in result.flags:
        for r in f["reps"]:
            flagged_by_rep.setdefault(r, []).append(f["code"])
    for rep in result.reps:
        rep["flags"] = flagged_by_rep.get(rep["rep"], [])

    out.update(reps=result.reps, flags=result.flags, set=set_metrics(result), extras=result.extras,
               side=result.side, view=result.view, signal=result.signal, fps=round(seq.fps, 2))
    return out


def analyze_video(path: str | Path, exercise: str, view: str, experience_level: str = "intermediate",
                  overlay_path: str | Path | None = None) -> dict:
    """Full pipeline on a video file (needs the MediaPipe model; see scripts/download_model.py)."""
    from .pose.landmarker import extract_sequence, write_overlay

    seq = extract_sequence(path)
    out = analyze_sequence(seq, exercise, view, experience_level)
    out["overlay_written"] = False
    if overlay_path and out["reps"]:
        bad = {i for r in out["reps"] if r["flags"] for i in range(r["start_frame"], r["end_frame"] + 1)}
        out["overlay_written"] = write_overlay(path, seq, overlay_path, flagged_frames=bad)
    return out
