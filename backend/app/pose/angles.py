"""Joint-angle helpers. All work on (..., 3) or (..., 2) arrays, y pointing DOWN."""
from __future__ import annotations

import numpy as np


def angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Angle at point `b` (degrees, 0..180) formed by a-b-c. Works on single points or (T, d) arrays."""
    a, b, c = (np.asarray(x, dtype=float) for x in (a, b, c))
    v1, v2 = a - b, c - b
    dot = np.sum(v1 * v2, axis=-1)
    n = np.linalg.norm(v1, axis=-1) * np.linalg.norm(v2, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.clip(dot / n, -1.0, 1.0)
    return np.degrees(np.arccos(cos))


def _angle_to_axis(v: np.ndarray, axis: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)[..., :2]
    dot = v @ axis
    n = np.linalg.norm(v, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.clip(dot / n, -1.0, 1.0)
    return np.degrees(np.arccos(cos))


def torso_angle_from_vertical(shoulder: np.ndarray, hip: np.ndarray) -> np.ndarray:
    """Angle (degrees) between the hip->shoulder line and the vertical axis. 0 = upright.

    Only x/y are used, so this is the lean seen in the image plane (y is down, so up is -y).
    """
    v = np.asarray(shoulder, dtype=float)[..., :2] - np.asarray(hip, dtype=float)[..., :2]
    return _angle_to_axis(v, np.array([0.0, -1.0]))


def segment_angle_from_down(top: np.ndarray, bottom: np.ndarray) -> np.ndarray:
    """Angle (degrees) between the top->bottom segment and straight down. Used for upper-arm drift."""
    v = np.asarray(bottom, dtype=float)[..., :2] - np.asarray(top, dtype=float)[..., :2]
    return _angle_to_axis(v, np.array([0.0, 1.0]))


def segment_length(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float), axis=-1)
