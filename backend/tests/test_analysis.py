"""Set metrics, form score, progress and the judgement rules."""
import pytest

from app.analysis import progress
from app.analysis.judgement import build_judgement, injury_relates
from app.analysis.metrics import form_score
from app.pipeline import analyze_sequence
from app.pose import synthetic as syn

PROFILE = {"age": 30, "goal": "strength", "experience_level": "intermediate", "body_weight_kg": 80,
           "injuries_or_limits": None}
INPUTS = {"exercise": "squat", "load_kg": 60, "rpe": 7, "pain_during_set": False}


def run(seq, exercise="squat", view="side", **kw):
    return analyze_sequence(seq, exercise, view, **kw)


def judge(analysis, profile=None, inputs=None, history=None):
    return build_judgement({**PROFILE, **(profile or {})}, {**INPUTS, **(inputs or {})}, analysis,
                           analysis["quality"], history)


def test_good_set_scores_high_and_bad_scores_lower():
    good = run(syn.gen_squat(min_knee=80))
    bad = run(syn.gen_squat(min_knee=115, lean=55, down_s=0.6, up_s=0.8))
    assert good["set"]["form_score"] >= 90
    assert bad["set"]["form_score"] < good["set"]["form_score"] - 25
    assert 0 <= bad["set"]["form_score"] <= 100


def test_form_score_without_reps_is_none():
    assert form_score([], [], None) is None


def test_velocity_loss_detected():
    # the lifting phase gets slower every rep (1.0 s -> 1.9 s)
    slowing = syn.gen_squat(n_reps=6, up_per_rep=[1.0, 1.1, 1.3, 1.5, 1.7, 1.9])
    assert run(slowing)["set"]["velocity_loss_pct"] > 25
    steady = syn.gen_squat(n_reps=6)
    assert run(steady)["set"]["velocity_loss_pct"] < 5


def test_set_metrics_shape():
    a = run(syn.gen_squat())
    s = a["set"]
    assert s["rep_count"] == 5 and s["depth_mean"] == pytest.approx(80, abs=3)
    assert a["reps"][0]["flags"] == []


def test_needs_reshoot_skips_analysis():
    seq = syn.gen_squat_front()
    a = run(seq, view="side")
    assert a["quality"]["needs_reshoot"] and a["reps"] == [] and a["set"] is None


def test_no_reps_marks_reshoot():
    seq = syn.gen_squat(n_reps=0)
    a = run(seq)
    assert a["quality"]["needs_reshoot"] and "count any reps" in a["quality"]["reason"]


# ------------------------------------------------------------------ judgement
def test_judgement_matches_spec_shape():
    j = judge(run(syn.gen_squat(min_knee=105)))
    for key in ("form_score", "flags", "fatigue", "relative_load", "safety", "progress_vs_last_3", "data_quality"):
        assert key in j
    assert j["relative_load"] == 0.75
    assert j["flags"][0]["code"] == "shallow_depth"
    assert j["safety"]["conservative_mode"] is False and j["max_load_increase_pct"] == 5.0


def test_pain_forces_conservative_and_zero_load_increase():
    j = judge(run(syn.gen_squat()), inputs={"pain_during_set": True})
    assert j["safety"]["pain_reported"] and j["safety"]["conservative_mode"]
    assert j["max_load_increase_pct"] == 0.0 and j["coach_attention"]


@pytest.mark.parametrize("profile,why", [
    ({"age": 67}, "65"),
    ({"goal": "rehab_return"}, "rehab"),
    ({"injuries_or_limits": "left knee pain"}, "injury"),
])
def test_conservative_triggers(profile, why):
    j = judge(run(syn.gen_squat()), profile=profile)
    assert j["safety"]["conservative_mode"] and j["max_load_increase_pct"] == 0.0, why


def test_unrelated_injury_is_not_conservative():
    assert not injury_relates("wrist sprain", "squat")
    assert injury_relates("wrist sprain", "pushup")
    j = judge(run(syn.gen_squat()), profile={"injuries_or_limits": "wrist sprain"})
    assert not j["safety"]["conservative_mode"]


def test_poor_data_quality_is_conservative():
    seq = syn.gen_squat()
    seq.vis[:, 25:29] = 0.1
    a = run(seq)
    j = judge(a)
    assert j["safety"]["conservative_mode"] and not j["data_quality"]["ok"]


def test_close_to_failure_needs_rpe_and_speed_loss():
    a = run(syn.gen_squat())
    a["set"]["velocity_loss_pct"] = 28.0
    assert judge(a, inputs={"rpe": 8})["fatigue"]["close_to_failure"] is True
    assert judge(a, inputs={"rpe": 5})["fatigue"]["close_to_failure"] is False


def test_beginner_gets_two_cues():
    assert judge(run(syn.gen_squat()), profile={"experience_level": "beginner"})["cue_limit"] == 2


def test_relative_load_uses_body_weight_today():
    j = judge(run(syn.gen_squat()), inputs={"body_weight_today_kg": 75, "load_kg": 75})
    assert j["relative_load"] == 1.0


# ------------------------------------------------------------------ progress
def pt(score, depth, rel, ex="squat"):
    return {"exercise": ex, "form_score": score, "depth": depth, "relative_load": rel, "date": None}


def test_progress_vs_last_3():
    cur = pt(80, 90, 0.8)
    hist = [pt(70, 96, 0.75), pt(72, 96, 0.75), pt(71, 96, 0.75), pt(10, 10, 0.1)]
    p = progress.compare_with_last_n(cur, hist, 3)
    assert p["form_score_change"] == 9 and p["depth_change_deg"] == -6.0 and p["relative_load_change"] == 0.05
    assert progress.compare_with_last_n(cur, []) is None
    assert progress.compare_with_last_n(cur, [pt(70, 96, 0.7, "pushup")]) is None


def test_trend_classification():
    assert progress.trend([pt(60, 0, 0), pt(65, 0, 0)]) == "not_enough_data"
    assert progress.trend([pt(60, 0, 0), pt(66, 0, 0), pt(75, 0, 0)]) == "improving"
    assert progress.trend([pt(80, 0, 0), pt(70, 0, 0), pt(62, 0, 0)]) == "declining"
    assert progress.trend([pt(70, 0, 0), pt(71, 0, 0), pt(69, 0, 0)]) == "stable"
