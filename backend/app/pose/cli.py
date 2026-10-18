"""Run the pose pipeline on a local video and print the metrics JSON.

    python -m app.pose.cli path/to/video.mp4 --exercise squat --view side
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="RepCheck pose pipeline on a local video")
    p.add_argument("video")
    p.add_argument("--exercise", choices=["squat", "pushup", "bicep_curl"], required=True)
    p.add_argument("--view", choices=["side", "front"], default="side")
    p.add_argument("--experience", choices=["beginner", "intermediate", "advanced"], default="intermediate")
    p.add_argument("--overlay", help="optional path to write a skeleton overlay mp4")
    p.add_argument("--signal", action="store_true", help="include the raw main signal in the output")
    args = p.parse_args(argv)

    from app.pipeline import analyze_video

    try:
        out = analyze_video(args.video, args.exercise, args.view, args.experience, overlay_path=args.overlay)
    except Exception as exc:  # friendly message for missing model / unreadable file
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not args.signal:
        out.pop("signal", None)
    print(json.dumps(out, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
