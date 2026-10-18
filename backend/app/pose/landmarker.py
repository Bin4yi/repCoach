"""MediaPipe PoseLandmarker wrapper (Tasks API, VIDEO running mode).

Turns a video file into a `PoseSequence`. Nothing here judges form; it only finds body points.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..config import get_settings
from .types import PoseSequence

MODEL_NAME = "pose_landmarker_full.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_full/float16/latest/pose_landmarker_full.task")
MAX_EDGE_PX = 640       # frames are downscaled before pose detection (speed)
HIGH_FPS = 30.0         # above this we only process every 2nd frame
N_LANDMARKS = 33

# Skeleton lines for the overlay video (index pairs)
CONNECTIONS = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
               (23, 25), (25, 27), (24, 26), (26, 28), (27, 29), (29, 31), (28, 30), (30, 32)]


class PoseModelMissing(RuntimeError):
    pass


def model_path() -> Path:
    return Path(get_settings().model_dir) / MODEL_NAME


def _build_landmarker():
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision

    path = model_path()
    if not path.exists():
        raise PoseModelMissing(
            f"Pose model not found at {path}. Run: python scripts/download_model.py")
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(path)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=2,  # 2 so we can notice a second person in the shot
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(options)


def _frame_step(fps: float) -> int:
    return 2 if fps > HIGH_FPS else 1


def _pick_main_person(poses) -> int:
    """Index of the person with the biggest body box (the one nearest the camera)."""
    best, best_area = 0, -1.0
    for i, lms in enumerate(poses):
        xs = [lm.x for lm in lms]
        ys = [lm.y for lm in lms]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if area > best_area:
            best, best_area = i, area
    return best


def extract_sequence(video_path: str | Path, max_seconds: float | None = None) -> PoseSequence:
    """Run pose detection over a video and return landmarks for every processed frame."""
    import mediapipe as mp

    max_seconds = max_seconds or get_settings().max_video_seconds
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("Could not open the video file.")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = _frame_step(src_fps)
    eff_fps = src_fps / step
    w0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h0 = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, MAX_EDGE_PX / max(w0, h0, 1))
    aspect = (w0 / h0) if h0 else 1.0

    img, world, vis, detected, multi, frame_ids = [], [], [], [], [], []
    with _build_landmarker() as landmarker:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok or i / src_fps > max_seconds:
                break
            if i % step == 0:
                if scale < 1.0:
                    frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = int(i / src_fps * 1000)  # must be strictly increasing
                res = landmarker.detect_for_video(mp_img, ts)
                if res.pose_landmarks:
                    k = _pick_main_person(res.pose_landmarks)
                    lms = res.pose_landmarks[k]
                    img.append([[lm.x * aspect, lm.y, lm.z] for lm in lms])
                    vis.append([lm.visibility for lm in lms])
                    if res.pose_world_landmarks:
                        wl = res.pose_world_landmarks[k]
                        world.append([[p.x, p.y, p.z] for p in wl])
                    else:
                        world.append([[np.nan] * 3] * N_LANDMARKS)
                    detected.append(True)
                    multi.append(len(res.pose_landmarks) > 1)
                else:
                    img.append([[np.nan] * 3] * N_LANDMARKS)
                    world.append([[np.nan] * 3] * N_LANDMARKS)
                    vis.append([0.0] * N_LANDMARKS)
                    detected.append(False)
                    multi.append(False)
                frame_ids.append(i)
            i += 1
    cap.release()

    img_a = np.array(img, dtype=float).reshape(-1, N_LANDMARKS, 3)
    world_a = np.array(world, dtype=float).reshape(-1, N_LANDMARKS, 3)
    has_world = bool(len(world_a)) and not np.all(np.isnan(world_a))
    return PoseSequence(
        img=img_a,
        vis=np.array(vis, dtype=float).reshape(-1, N_LANDMARKS),
        fps=float(eff_fps),
        world=world_a if has_world else None,
        detected=np.array(detected, dtype=bool),
        multi_person=np.array(multi, dtype=bool),
        frame_size=(w0, h0),
        meta={"frame_ids": frame_ids, "aspect": aspect, "step": step},
    )


def write_overlay(video_path: str | Path, seq: PoseSequence, out_path: str | Path,
                  flagged_frames: set[int] | None = None) -> bool:
    """Draw the skeleton on the video and save a short mp4. Returns False if it could not be written.

    `flagged_frames` (indices into seq) are drawn in red so the coach can spot bad reps.
    """
    frame_ids = seq.meta.get("frame_ids")
    if not frame_ids:
        return False
    aspect = seq.meta.get("aspect", 1.0)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False
    w0, h0 = seq.frame_size
    scale = min(1.0, MAX_EDGE_PX / max(w0, h0, 1))
    size = (max(2, int(w0 * scale) // 2 * 2), max(2, int(h0 * scale) // 2 * 2))
    writer = None
    for codec in ("avc1", "mp4v"):  # avc1 plays in browsers; not always available in OpenCV builds
        w = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*codec), seq.fps, size)
        if w.isOpened():
            writer = w
            break
    if writer is None:
        cap.release()
        return False

    idx_by_frame = {f: k for k, f in enumerate(frame_ids)}
    flagged_frames = flagged_frames or set()
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        k = idx_by_frame.get(i)
        if k is not None:
            frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
            color = (60, 60, 230) if k in flagged_frames else (80, 200, 80)  # BGR
            pts = seq.img[k, :, :2]
            for a, b in CONNECTIONS:
                if seq.vis[k, a] > 0.5 and seq.vis[k, b] > 0.5 and not np.isnan(pts[[a, b]]).any():
                    pa = (int(pts[a, 0] / aspect * size[0]), int(pts[a, 1] * size[1]))
                    pb = (int(pts[b, 0] / aspect * size[0]), int(pts[b, 1] * size[1]))
                    cv2.line(frame, pa, pb, color, 3)
            writer.write(frame)
        i += 1
    writer.release()
    cap.release()
    return True
