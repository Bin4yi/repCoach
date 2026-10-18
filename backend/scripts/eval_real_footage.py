"""Regression check on REAL footage (openly licensed clips; downloaded on demand, never committed).

    python scripts/eval_real_footage.py            # download missing clips, run the pipeline, compare
Expected values were checked by hand against each clip's signal plot. Needs the MediaPipe model.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import analyze_video  # noqa: E402

DIR = Path(__file__).resolve().parents[2] / "test-footage"
UA = {"User-Agent": "RepCheck-eval/0.1"}

# file, source URL, license, exercise, view, expected
CASES = [
    ("kb_racked_squats_side.webm",
     "https://upload.wikimedia.org/wikipedia/commons/9/93/Kettlebell_Racked_Squats_%28side_view%29.webm",
     "CC BY-SA 4.0 (Wikimedia Commons)", "squat", "side", {"reps": 6, "no_flags": ["shallow_depth", "excess_forward_lean"]}),
    ("interval_push_ups.webm",
     "https://upload.wikimedia.org/wikipedia/commons/9/98/Interval_Push-ups.webm",
     "CC BY-SA 4.0 (Wikimedia Commons)", "pushup", "side", {"reps": 6, "no_flags": ["partial_range", "hip_sag"]}),
    ("kb_goblet_squat.webm",
     "https://upload.wikimedia.org/wikipedia/commons/c/c3/Kettlebell_Goblet_Squat.webm",
     "CC BY-SA 4.0 (Wikimedia Commons)", "squat", "front", {"reps": 2, "no_flags": ["knee_cave"]}),
    ("github_pushup.mp4",
     "https://raw.githubusercontent.com/airscholar/AI-Workout-Manager/HEAD/assets/pushup.mp4",
     "see github.com/airscholar/AI-Workout-Manager", "pushup", "side", {"reshoot": True}),
]


def fetch(name: str, url: str) -> Path:
    p = DIR / name
    if not p.exists():
        DIR.mkdir(exist_ok=True)
        try:
            p.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=UA)).read())
        except Exception:
            # Commons hash paths can move: look the file up by title
            import urllib.parse
            title = "File:" + urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")
            q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url", "format": "json"})
            d = json.load(urllib.request.urlopen(urllib.request.Request("https://commons.wikimedia.org/w/api.php?" + q, headers=UA)))
            real = next(iter(d["query"]["pages"].values()))["imageinfo"][0]["url"]
            p.write_bytes(urllib.request.urlopen(urllib.request.Request(real, headers=UA)).read())
    return p


def main() -> int:
    failures = 0
    for name, url, lic, exercise, view, exp in CASES:
        path = fetch(name, url)
        out = analyze_video(path, exercise, view)
        reps = (out.get("set") or {}).get("rep_count")
        flags = {f["code"] for f in out["flags"]}
        problems = []
        if exp.get("reshoot") is not None and out["quality"]["needs_reshoot"] != exp["reshoot"]:
            problems.append(f"reshoot={out['quality']['needs_reshoot']} expected {exp['reshoot']}")
        if "reps" in exp and reps != exp["reps"]:
            problems.append(f"reps={reps} expected {exp['reps']}")
        bad = flags & set(exp.get("no_flags", []))
        if bad:
            problems.append(f"unexpected flags {sorted(bad)}")
        status = "OK  " if not problems else "FAIL"
        failures += bool(problems)
        print(f"{status} {name:32s} {exercise:10s} {view:5s} reps={reps} flags={sorted(flags)} {'; '.join(problems)}")
        print(f"     source: {url} ({lic})")
    print(f"\n{len(CASES) - failures}/{len(CASES)} real-footage cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
