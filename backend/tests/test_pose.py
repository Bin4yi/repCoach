"""Angle helpers, rep counting, smoothing, quality and each exercise analyzer on synthetic skeletons."""
import numpy as np
import pytest

from app.pose import synthetic as syn
from app.pose.angles import angle, segment_angle_from_down, torso_angle_from_vertical
from app.pose.exercises import AnalysisContext, get_analyzer
from app.pose.exercises.base import detect_reps
from app.pose.quality import assess_quality
from app.pose.smoothing import smooth_array, smooth_sequence


def flags(res):
    return {f["code"]: f for f in res.flags}


# ------------------------------------------------------------------ angles
def test_angle_known_values():
    assert angle([1, 0], [0, 0], [0, 1]) == pytest.approx(90)
    assert angle([1, 0], [0, 0], [-1, 0]) == pytest.approx(180)
    assert angle([1, 0], [0, 0], [1, 1]) == pytest.approx(45)
    assert angle([0, 0, 1], [0, 0, 0], [0, 1, 0]) == pytest.approx(90)


def test_angle_vectorised():
    a = np.array([[1, 0], [1, 0]])
    b = np.zeros((2, 2))
    c = np.array([[0, 1], [-1, 0]])
    assert angle(a, b, c) == pytest.approx([90, 180])


def test_torso_angle_from_vertical():
    # y is down: shoulder directly above hip = upright
    assert torso_angle_from_vertical([0, 0], [0, 1]) == pytest.approx(0)
    assert torso_angle_from_vertical([1, 0], [0, 1]) == pytest.approx(45)
    assert torso_angle_from_vertical([1, 1], [0, 1]) == pytest.approx(90)


def test_segment_angle_from_down():
    assert segment_angle_from_down([0, 0], [0, 1]) == pytest.approx(0)
    assert segment_angle_from_down([0, 0], [1, 1]) == pytest.approx(45)


# ------------------------------------------------------------------ rep detection
@pytest.mark.parametrize("n", [1, 3, 5, 8])
def test_rep_counting_on_sine(n):
    fps = 30
    t = np.arange(0, n * 3.0 + 2, 1 / fps)
    sig = 130 + 50 * np.cos(2 * np.pi * t / 3.0)           # starts at the top, one rep per 3 s
    sig[t > n * 3.0] = 180
    reps = detect_reps(sig, fps, min_prominence=25, min_rep_seconds=1.0)
    assert len(reps) == n
    assert all(r.start < r.bottom < r.end for r in reps)


def test_wobble_is_not_a_rep():
    fps = 30
    t = np.arange(0, 6, 1 / fps)
    sig = 170 + 3 * np.sin(2 * np.pi * t * 2)
    assert detect_reps(sig, fps, 25, 1.0) == []


def test_squat_five_reps_synthetic():
    res = get_analyzer("squat").analyze(syn.gen_squat(n_reps=5), "side")
    assert len(res.reps) == 5


# ------------------------------------------------------------------ smoothing / quality
def test_smoothing_fills_short_gaps_only():
    t = 60
    pts = np.zeros((t, 33, 3))
    pts[:, 0, 0] = np.linspace(0, 1, t)
    vis = np.ones((t, 33))
    vis[10:13, 0] = 0.1      # 3-frame gap: filled
    vis[30:40, 0] = 0.1      # 10-frame gap: stays missing
    out = smooth_array(pts, vis, fps=30)
    assert not np.isnan(out[11, 0, 0])
    assert np.isnan(out[35, 0, 0])


def test_smoothing_reduces_noise():
    seq = syn.gen_squat(noise=0.01, seed=1)
    clean = syn.gen_squat()
    sm = smooth_sequence(seq)
    assert np.nanmean(np.abs(sm.img - clean.img)) < np.mean(np.abs(seq.img - clean.img))


def test_quality_ok_for_good_side_video():
    q = assess_quality(syn.gen_squat(), "squat", "side")
    assert q.ok and not q.needs_reshoot and q.view_estimate == "side"


def test_quality_wrong_view_needs_reshoot():
    q = assess_quality(syn.gen_squat_front(), "squat", "side")
    assert q.needs_reshoot and "side" in q.reason


def test_quality_low_visibility_needs_reshoot():
    seq = syn.gen_squat()
    seq.vis[:, 25:29] = 0.1  # knees and ankles hidden
    q = assess_quality(seq, "squat", "side")
    assert q.needs_reshoot and "whole body" in q.reason


def test_quality_two_people():
    seq = syn.gen_squat()
    seq.multi_person[:] = True
    assert "one person" in assess_quality(seq, "squat", "side").reason


# ------------------------------------------------------------------ squat
def test_squat_good_form_has_no_flags():
    res = get_analyzer("squat").analyze(syn.gen_squat(min_knee=80, lean=35), "side")
    assert res.flags == []
    assert res.reps[0]["depth_angle"] == pytest.approx(80, abs=3)
    assert res.reps[0]["eccentric_s"] == pytest.approx(2.0, abs=0.4)


def test_squat_shallow():
    res = get_analyzer("squat").analyze(syn.gen_squat(min_knee=110), "side")
    f = flags(res)["shallow_depth"]
    assert f["reps"] == [1, 2, 3, 4, 5] and f["severity"] == "high"
    assert "target < 95" in f["evidence"]


def test_squat_beginner_gets_more_depth_slack():
    seq = syn.gen_squat(min_knee=100)
    assert "shallow_depth" in flags(get_analyzer("squat").analyze(seq, "side"))
    assert "shallow_depth" not in flags(get_analyzer("squat").analyze(seq, "side", AnalysisContext("beginner")))


def test_squat_forward_lean_and_limb_ratio():
    seq = syn.gen_squat(lean=52)
    assert "excess_forward_lean" in flags(get_analyzer("squat").analyze(seq, "side"))
    # a long-femur lifter is allowed more lean: same 52 deg lean is fine at a high femur/torso ratio
    long_femur = syn.gen_squat(lean=52, femur_ratio=1.25)
    res = get_analyzer("squat").analyze(long_femur, "side")
    assert res.extras["femur_torso_ratio"] > 1.05
    assert res.extras["lean_limit_deg"] > 50
    assert "excess_forward_lean" not in flags(res)


def test_squat_rushed_eccentric():
    res = get_analyzer("squat").analyze(syn.gen_squat(down_s=0.6, up_s=0.8), "side")
    assert "rushed_eccentric" in flags(res)


def test_squat_depth_drops_with_fatigue():
    seq = syn.gen_squat(n_reps=6, min_knee_per_rep=[80, 80, 85, 95, 105, 110])
    res = get_analyzer("squat").analyze(seq, "side")
    f = flags(res)["depth_drops_with_fatigue"]
    assert f["reps"] == [5, 6]


def test_squat_balance_asymmetry():
    res = get_analyzer("squat").analyze(syn.gen_squat(left_extra_deg=20), "side")
    assert res.balance and res.balance["diff_deg"] > 5


def test_squat_front_knee_cave():
    good = get_analyzer("squat").analyze(syn.gen_squat_front(), "front")
    assert len(good.reps) == 5 and "knee_cave" not in flags(good)
    bad = get_analyzer("squat").analyze(syn.gen_squat_front(knee_cave_m=0.06), "front")
    assert "knee_cave" in flags(bad)


def test_squat_facing_left_matches_facing_right():
    a = get_analyzer("squat").analyze(syn.gen_squat(facing=1.0, min_knee=105), "side")
    b = get_analyzer("squat").analyze(syn.gen_squat(facing=-1.0, min_knee=105), "side")
    assert [f["code"] for f in a.flags] == [f["code"] for f in b.flags]
    assert a.reps[0]["depth_angle"] == pytest.approx(b.reps[0]["depth_angle"], abs=0.5)


# ------------------------------------------------------------------ push-up
def test_pushup_good_form():
    res = get_analyzer("pushup").analyze(syn.gen_pushup(), "side")
    assert len(res.reps) == 5 and res.flags == []
    assert res.reps[0]["depth_angle"] == pytest.approx(75, abs=4)


def test_pushup_partial_range():
    assert "partial_range" in flags(get_analyzer("pushup").analyze(syn.gen_pushup(min_elbow=120), "side"))


def test_pushup_hip_sag_and_high():
    sag = flags(get_analyzer("pushup").analyze(syn.gen_pushup(hip_offset=0.12), "side"))
    assert "hip_sag" in sag and "hips_high" not in sag
    high = flags(get_analyzer("pushup").analyze(syn.gen_pushup(hip_offset=-0.12), "side"))
    assert "hips_high" in high and "hip_sag" not in high


def test_pushup_no_lockout():
    res = get_analyzer("pushup").analyze(syn.gen_pushup(lockout=140, min_elbow=80), "side")
    assert "no_lockout" in flags(res)


# ------------------------------------------------------------------ curl
def test_curl_good_form():
    res = get_analyzer("bicep_curl").analyze(syn.gen_curl(), "side")
    assert len(res.reps) == 6 and res.flags == []


def test_curl_partial_range():
    res = get_analyzer("bicep_curl").analyze(syn.gen_curl(min_elbow=85, max_elbow=130), "side")
    assert "partial_range" in flags(res)


def test_curl_elbow_drift_and_body_swing():
    assert "elbow_drift" in flags(get_analyzer("bicep_curl").analyze(syn.gen_curl(drift_deg=35), "side"))
    assert "body_swing" in flags(get_analyzer("bicep_curl").analyze(syn.gen_curl(swing_deg=20), "side"))
