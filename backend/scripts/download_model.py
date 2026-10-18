"""Download the MediaPipe pose model into backend/models/ (cached; safe to re-run)."""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pose.landmarker import MODEL_URL, model_path  # noqa: E402


def main() -> int:
    dest = model_path()
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"Model already cached: {dest}")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {MODEL_URL}\n  -> {dest}")
    try:
        urllib.request.urlretrieve(MODEL_URL, dest)
    except Exception as exc:  # network problems should not crash a docker build
        print(f"Download failed: {exc}")
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
