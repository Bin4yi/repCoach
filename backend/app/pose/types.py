"""Shared pose data types and MediaPipe landmark indices."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# MediaPipe Pose landmark indices (33-point model)
NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_HEEL, R_HEEL = 29, 30
L_TOE, R_TOE = 31, 32

# Per-side landmark index maps. Side "L"/"R" refers to the person's left/right.
SIDES = {
    "L": dict(shoulder=L_SHOULDER, elbow=L_ELBOW, wrist=L_WRIST, hip=L_HIP,
              knee=L_KNEE, ankle=L_ANKLE, heel=L_HEEL, toe=L_TOE),
    "R": dict(shoulder=R_SHOULDER, elbow=R_ELBOW, wrist=R_WRIST, hip=R_HIP,
              knee=R_KNEE, ankle=R_ANKLE, heel=R_HEEL, toe=R_TOE),
}


@dataclass
class PoseSequence:
    """Landmarks for one video.

    Coordinates are y-DOWN (like images). `img` is image-plane (x scaled by aspect
    ratio so distances are not distorted); `world` is MediaPipe metric world
    landmarks when available. Angles use `pts` (world if present, else img).
    """

    img: np.ndarray                      # (T, 33, 3)
    vis: np.ndarray                      # (T, 33)
    fps: float
    world: np.ndarray | None = None      # (T, 33, 3)
    detected: np.ndarray | None = None   # (T,) bool: a person was found in the frame
    multi_person: np.ndarray | None = None  # (T,) bool: more than one person in the frame
    frame_size: tuple[int, int] = (0, 0)  # (width, height) of source frames
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.detected is None:
            self.detected = np.ones(len(self.img), dtype=bool)
        if self.multi_person is None:
            self.multi_person = np.zeros(len(self.img), dtype=bool)

    @property
    def pts(self) -> np.ndarray:
        return self.world if self.world is not None else self.img

    @property
    def n_frames(self) -> int:
        return len(self.img)

    @property
    def duration_s(self) -> float:
        return self.n_frames / self.fps if self.fps else 0.0

    def near_side(self) -> str:
        """Side of the body closest to the camera = higher mean visibility."""
        scores = {}
        for s, idx in SIDES.items():
            ids = [idx["shoulder"], idx["hip"], idx["knee"], idx["ankle"], idx["elbow"], idx["wrist"]]
            scores[s] = float(np.nanmean(self.vis[:, ids]))
        return "L" if scores["L"] >= scores["R"] else "R"

    def joint(self, side: str, name: str) -> np.ndarray:
        """(T, 3) trajectory of one joint on one side."""
        return self.pts[:, SIDES[side][name], :]

    def facing_sign(self, side: str) -> float:
        """+1 if the person faces +x (right) in the image, else -1. Uses toe vs heel."""
        toe = self.joint(side, "toe")[:, 0]
        heel = self.joint(side, "heel")[:, 0]
        d = float(np.nanmedian(toe - heel))
        if abs(d) > 1e-6:
            return 1.0 if d > 0 else -1.0
        nose = self.pts[:, NOSE, 0]
        hip = self.joint(side, "hip")[:, 0]
        return 1.0 if float(np.nanmedian(nose - hip)) >= 0 else -1.0
