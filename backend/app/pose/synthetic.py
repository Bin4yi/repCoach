"""Synthetic skeleton generators (forward kinematics) for tests, demo data and the seed script.

These produce `PoseSequence` objects that look like cleaned MediaPipe output, so the real
analyzers can be exercised without a video. They are DEMO DATA, never real measurements.

Conventions: y points DOWN, the ground is y = 1.8, person is built facing +x and mirrored if
`facing = -1`. Units are roughly metres.
"""
from __future__ import annotations

import math

import numpy as np

from .types import PoseSequence, SIDES

GROUND = 1.8
SHIN, THIGH, TORSO = 0.45, 0.45, 0.50
UPPER_ARM, FOREARM = 0.30, 0.27


def _u(theta_deg: float) -> np.ndarray:
    """Unit vector pointing 'up' tilted theta degrees toward +x (y is down)."""
    t = math.radians(theta_deg)
    return np.array([math.sin(t), -math.cos(t)])


def rep_profile(n_reps: int, fps: float, down_s=2.0, up_s=1.0, pause_s=0.3, rest_s=0.4,
                lead_s=1.0, tail_s=1.0, down_per_rep=None, up_per_rep=None):
    """Return (u, rep_id): u in [0,1] (0 = start position, 1 = deepest point), rep_id per frame (-1 = idle)."""
    chunks_u, chunks_id = [], []

    def add(vals, rid):
        chunks_u.append(np.asarray(vals, dtype=float))
        chunks_id.append(np.full(len(vals), rid, dtype=int))

    add(np.zeros(int(lead_s * fps)), -1)
    for i in range(n_reps):
        d = down_per_rep[i] if down_per_rep else down_s
        u_ = up_per_rep[i] if up_per_rep else up_s
        nd, nu = max(2, int(d * fps)), max(2, int(u_ * fps))
        add(0.5 * (1 - np.cos(np.linspace(0, math.pi, nd, endpoint=False))), i)   # eccentric
        add(np.ones(int(pause_s * fps)), i)                                         # pause at bottom
        add(0.5 * (1 + np.cos(np.linspace(0, math.pi, nu, endpoint=False))), i)   # concentric
        add(np.zeros(int(rest_s * fps)), i if i < n_reps - 1 else -1)
    add(np.zeros(int(tail_s * fps)), -1)
    return np.concatenate(chunks_u), np.concatenate(chunks_id)


def _per_rep(value, n_reps, default):
    if value is None:
        return [default] * n_reps
    if isinstance(value, (int, float)):
        return [float(value)] * n_reps
    return list(value)


def _frame_values(per_rep, rep_id, idle_value):
    arr = np.array(per_rep, dtype=float)
    if arr.size == 0:
        return np.full(len(rep_id), idle_value)
    return np.where(rep_id >= 0, arr[np.clip(rep_id, 0, len(arr) - 1)], idle_value)


def _finish(frames: list[dict], fps: float, facing: float, near="L", far_vis=0.9, noise=0.0, seed=0,
            side_view=True) -> PoseSequence:
    """frames: list of {landmark_index: (x, y)} -> PoseSequence (mirrored by `facing`, both sides filled)."""
    rng = np.random.default_rng(seed)
    t = len(frames)
    img = np.zeros((t, 33, 3))
    vis = np.full((t, 33), 0.99)
    for i, f in enumerate(frames):
        for idx, (x, y, *z) in f.items():
            img[i, idx] = (x * facing + 0.5, y, z[0] if z else 0.0)
    if noise:
        img[:, :, :2] += rng.normal(0, noise, size=img[:, :, :2].shape)
    far_ids = list(SIDES["R" if near == "L" else "L"].values())
    if side_view:
        vis[:, far_ids] = far_vis
    return PoseSequence(img=img, vis=vis, fps=fps, frame_size=(1280, 720), meta={"synthetic": True})


def _both_sides(frame: dict, joints: dict[str, np.ndarray], right_joints: dict[str, np.ndarray] | None = None):
    """Write named joints for both sides (side view: same x/y, opposite z)."""
    for side, z in (("L", -0.05), ("R", 0.05)):
        src = joints if side == "L" or right_joints is None else right_joints
        for name, p in src.items():
            frame[SIDES[side][name]] = (float(p[0]), float(p[1]), z)


# --------------------------------------------------------------------------- squat

def gen_squat(n_reps=5, fps=30.0, min_knee=80.0, lean=35.0, shin_lean=25.0, down_s=2.0, up_s=1.0,
              pause_s=0.3, min_knee_per_rep=None, lean_per_rep=None, down_per_rep=None, up_per_rep=None,
              femur_ratio=1.0, noise=0.0, seed=0, facing=1.0, left_extra_deg=0.0) -> PoseSequence:
    """Side-view squat. min_knee = knee angle at the bottom (smaller = deeper)."""
    u, rid = rep_profile(n_reps, fps, down_s, up_s, pause_s, down_per_rep=down_per_rep, up_per_rep=up_per_rep)
    mk = _frame_values(_per_rep(min_knee_per_rep, n_reps, min_knee), rid, 180.0)
    ln = _frame_values(_per_rep(lean_per_rep, n_reps, lean), rid, 0.0)
    thigh = THIGH * femur_ratio
    frames = []
    for i in range(len(u)):
        def build(extra):
            k = 180.0 - u[i] * (180.0 - mk[i]) + extra * u[i]
            s = u[i] * shin_lean
            tt = s - (180.0 - k)
            tau = u[i] * ln[i]
            ankle = np.array([0.0, GROUND])
            knee = ankle + SHIN * _u(s)
            hip = knee + thigh * _u(tt)
            sh = hip + TORSO * _u(tau)
            return dict(ankle=ankle, knee=knee, hip=hip, shoulder=sh,
                        heel=ankle + np.array([-0.07, 0.04]), toe=ankle + np.array([0.20, 0.05]),
                        elbow=sh + np.array([0.08, 0.26]), wrist=sh + np.array([0.30, 0.10]))
        left, right = build(left_extra_deg), build(0.0)
        f = {}
        _both_sides(f, left, right)
        f[0] = (left["shoulder"][0] + 0.10, left["shoulder"][1] - 0.22, 0.0)  # nose
        frames.append(f)
    return _finish(frames, fps, facing, noise=noise, seed=seed)


def gen_squat_front(n_reps=5, fps=30.0, knee_cave_m=0.0, depth=0.35, down_s=2.0, up_s=1.0,
                    noise=0.0, seed=0) -> PoseSequence:
    """Front-view squat. knee_cave_m = how far (metres) the knees collapse inward at the bottom."""
    u, rid = rep_profile(n_reps, fps, down_s, up_s)
    frames = []
    for i in range(len(u)):
        f = {}
        hip_y = 0.9 + depth * u[i]
        sh_y = hip_y - 0.5
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            knee_x = 0.145 - knee_cave_m * u[i]
            pts = dict(shoulder=(sgn * 0.20, sh_y), hip=(sgn * 0.12, hip_y), knee=(sgn * knee_x, 1.35),
                       ankle=(sgn * 0.17, GROUND), heel=(sgn * 0.17, GROUND + 0.04), toe=(sgn * 0.19, GROUND + 0.05),
                       elbow=(sgn * 0.24, sh_y + 0.25), wrist=(sgn * 0.26, sh_y + 0.5))
            for name, (x, y) in pts.items():
                f[SIDES[side][name]] = (x, y, 0.0)
        f[0] = (0.0, sh_y - 0.25, 0.0)
        frames.append(f)
    return _finish(frames, fps, 1.0, noise=noise, seed=seed, side_view=False)


# --------------------------------------------------------------------------- push-up

def gen_pushup(n_reps=5, fps=30.0, min_elbow=75.0, lockout=172.0, hip_offset=0.0, down_s=1.5, up_s=1.0,
               min_elbow_per_rep=None, noise=0.0, seed=0, facing=1.0, body_len=1.4) -> PoseSequence:
    """Side-view push-up. hip_offset > 0 = hips sag (down), < 0 = hips piked (up), as a fraction of body length."""
    u, rid = rep_profile(n_reps, fps, down_s, up_s, pause_s=0.2)
    me = _frame_values(_per_rep(min_elbow_per_rep, n_reps, min_elbow), rid, lockout)
    frames = []
    wrist = np.array([0.0, GROUND - 0.05])
    for i in range(len(u)):
        e = lockout - u[i] * (lockout - me[i])
        d = math.sqrt(UPPER_ARM ** 2 + FOREARM ** 2 - 2 * UPPER_ARM * FOREARM * math.cos(math.radians(e)))
        sh = wrist + np.array([0.0, -d])
        cos_a = (FOREARM ** 2 + d ** 2 - UPPER_ARM ** 2) / (2 * FOREARM * d)
        a = math.acos(max(-1.0, min(1.0, cos_a)))
        elbow = wrist + FOREARM * np.array([-math.sin(a), -math.cos(a)])
        dy = GROUND - sh[1]
        ankle = np.array([sh[0] - math.sqrt(max(body_len ** 2 - dy ** 2, 1e-6)), GROUND])
        hip = (sh + ankle) / 2 + np.array([0.0, hip_offset * body_len])
        knee = hip + (ankle - hip) * 0.5
        joints = dict(shoulder=sh, elbow=elbow, wrist=wrist, hip=hip, knee=knee, ankle=ankle,
                      heel=ankle + np.array([0.08, -0.03]), toe=ankle + np.array([-0.12, 0.0]))
        f = {}
        _both_sides(f, joints)
        f[0] = (sh[0] + 0.18, sh[1] - 0.04, 0.0)
        frames.append(f)
    return _finish(frames, fps, facing, noise=noise, seed=seed)


# --------------------------------------------------------------------------- bicep curl

def gen_curl(n_reps=6, fps=30.0, min_elbow=40.0, max_elbow=165.0, drift_deg=0.0, swing_deg=0.0,
             down_s=1.5, up_s=1.2, noise=0.0, seed=0, facing=1.0) -> PoseSequence:
    """Side-view standing curl. u=1 is the top of the curl (elbow most bent)."""
    u, rid = rep_profile(n_reps, fps, down_s=up_s, up_s=down_s, pause_s=0.2)
    frames = []
    hip = np.array([0.0, 0.95])
    for i in range(len(u)):
        e = max_elbow - u[i] * (max_elbow - min_elbow)
        tau = u[i] * swing_deg
        dr = math.radians(u[i] * drift_deg)
        sh = hip + TORSO * _u(tau)
        elbow = sh + UPPER_ARM * np.array([math.sin(dr), math.cos(dr)])
        v1 = (sh - elbow) / np.linalg.norm(sh - elbow)
        th = math.radians(e)
        v2 = np.array([v1[0] * math.cos(th) - v1[1] * math.sin(th), v1[0] * math.sin(th) + v1[1] * math.cos(th)])
        wrist = elbow + FOREARM * v2
        knee = np.array([0.0, 1.4])
        ankle = np.array([0.0, GROUND])
        joints = dict(shoulder=sh, elbow=elbow, wrist=wrist, hip=hip, knee=knee, ankle=ankle,
                      heel=ankle + np.array([-0.07, 0.04]), toe=ankle + np.array([0.20, 0.05]))
        f = {}
        _both_sides(f, joints)
        f[0] = (sh[0] + 0.05, sh[1] - 0.22, 0.0)
        frames.append(f)
    return _finish(frames, fps, facing, noise=noise, seed=seed)
