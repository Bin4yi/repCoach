"""LLM layer with a mocked Ollama: valid JSON, invalid-JSON retry, invented-number check, load clamp, safety."""
import json

import httpx
import pytest

from app.analysis.judgement import build_judgement
from app.llm import reports
from app.llm.ollama_client import OllamaClient, OllamaError, pick_model
from app.llm.schemas import ProgressSummary, SessionFeedback, WeekPlan, json_schema
from app.pipeline import analyze_sequence
from app.pose import synthetic as syn

PROFILE = {"name": "Secret Name", "age": 30, "goal": "strength", "experience_level": "intermediate",
           "body_weight_kg": 80, "training_days_per_week": 3, "injuries_or_limits": None, "equipment": ["barbell"]}
INPUTS = {"exercise": "squat", "camera_view": "side", "load_kg": 60, "rpe": 7, "pain_during_set": False}


def make_judgement(profile=None, inputs=None, min_knee=105):
    a = analyze_sequence(syn.gen_squat(min_knee=min_knee), "squat", "side")
    j = build_judgement({**PROFILE, **(profile or {})}, {**INPUTS, **(inputs or {})}, a, a["quality"], [])
    return j, a["set"]


def good_feedback(**over):
    d = {"summary": "Squat set with a shallow depth.", "what_went_well": ["Steady tempo."],
         "fix_next_time": [{"cue": "Sit deeper", "why": "Knee angle was 105° but the target is under 95°.", "reps": [1, 2]}],
         "coach_only_notes": [], "client_message": "Nice set! Try to sit a little deeper next time."}
    d.update(over)
    return d


class FakeLLM:
    """Returns queued dicts/exceptions; records prompts."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    async def chat_json(self, system, user, model_cls):
        self.prompts.append((system, user))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return model_cls.model_validate(r)


# ------------------------------------------------------------------ OllamaClient
def transport(*contents):
    """MockTransport that answers /api/chat with successive message contents (str) or status codes (int)."""
    calls = {"n": 0, "bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "gemma3:4b"}]})
        calls["bodies"].append(json.loads(request.content))
        c = contents[min(calls["n"], len(contents) - 1)]
        calls["n"] += 1
        if isinstance(c, int):
            return httpx.Response(c, text="boom")
        return httpx.Response(200, json={"message": {"role": "assistant", "content": c}})

    return httpx.MockTransport(handler), calls


async def test_client_valid_json_and_request_shape():
    t, calls = transport(json.dumps(good_feedback()))
    out = await OllamaClient("http://x", "gemma3:4b", transport=t).chat_json("sys", "user", SessionFeedback)
    assert out.client_message.startswith("Nice")
    body = calls["bodies"][0]
    assert body["model"] == "gemma3:4b" and body["stream"] is False
    assert body["options"]["temperature"] == 0.3
    assert body["format"]["type"] == "object" and "$ref" not in json.dumps(body["format"])


async def test_client_invalid_json_retries_once_with_error_attached():
    t, calls = transport("not json at all", json.dumps(good_feedback()))
    out = await OllamaClient("http://x", "m", transport=t).chat_json("s", "u", SessionFeedback)
    assert out.summary
    assert calls["n"] == 2
    retry_msgs = calls["bodies"][1]["messages"]
    assert retry_msgs[-1]["role"] == "user" and "not valid" in retry_msgs[-1]["content"]


async def test_client_schema_violation_also_retries_then_fails():
    t, calls = transport(json.dumps({"summary": "x"}))
    with pytest.raises(OllamaError):
        await OllamaClient("http://x", "m", transport=t).chat_json("s", "u", SessionFeedback)
    assert calls["n"] == 2


async def test_client_retries_server_errors():
    t, calls = transport(500, 500, json.dumps(good_feedback()))
    out = await OllamaClient("http://x", "m", transport=t).chat_json("s", "u", SessionFeedback)
    assert out.summary and calls["n"] == 3


async def test_client_gives_up_after_retries():
    t, calls = transport(500)
    with pytest.raises(OllamaError):
        await OllamaClient("http://x", "m", transport=t).chat_json("s", "u", SessionFeedback)
    assert calls["n"] == 3


async def test_health_and_model_pick():
    t, _ = transport("")
    c = OllamaClient("http://x", "gemma3:12b", transport=t)
    assert (await c.health())["ok"]
    assert await c.use_best_model() == "gemma3:4b"
    assert pick_model("x", ["llama3", "gemma3:4b", "gemma3n:e2b"]) == "gemma3n:e2b"
    assert pick_model("llama3", ["llama3"]) == "llama3"


def test_json_schema_is_inlined():
    s = json_schema(WeekPlan)
    assert "$defs" not in s and "$ref" not in json.dumps(s)
    assert "load_change_pct" in s["properties"]["sessions"]["items"]["properties"]


# ------------------------------------------------------------------ feedback generation
async def test_feedback_accepts_valid_output():
    j, s = make_judgement()
    r = await reports.generate_feedback(FakeLLM(good_feedback()), PROFILE, INPUTS, j, s)
    assert r["source"] == "gemma" and r["warnings"] == []
    assert r["draft"]["fix_next_time"][0]["reps"] == [1, 2]


async def test_feedback_invented_number_regenerates_then_succeeds():
    j, s = make_judgement()
    bad = good_feedback(client_message="Great set! Your knee angle should reach 61 degrees.")
    llm = FakeLLM(bad, good_feedback())
    r = await reports.generate_feedback(llm, PROFILE, INPUTS, j, s)
    assert r["source"] == "gemma" and len(llm.prompts) == 2
    assert "61" in llm.prompts[1][1] and "not in the data" in llm.prompts[1][1]
    assert "61" not in json.dumps(r["draft"])


async def test_feedback_invented_number_twice_falls_back_to_template():
    j, s = make_judgement()
    bad = good_feedback(summary="You hit 999 kg.")
    r = await reports.generate_feedback(FakeLLM(bad, bad), PROFILE, INPUTS, j, s)
    assert r["source"] == "template"
    assert "999" not in json.dumps(r["draft"])
    assert "deeper" in r["draft"]["client_message"].lower()
    assert len(r["draft"]["client_message"].split()) <= 120


async def test_feedback_numbers_from_data_are_allowed():
    j, s = make_judgement()
    ok = good_feedback(client_message="Your form score was %d. Nice work!" % j["form_score"])
    r = await reports.generate_feedback(FakeLLM(ok), PROFILE, INPUTS, j, s)
    assert r["source"] == "gemma"


async def test_feedback_falls_back_when_ollama_down():
    j, s = make_judgement()
    r = await reports.generate_feedback(FakeLLM(OllamaError("down")), PROFILE, INPUTS, j, s)
    assert r["source"] == "template"
    assert (await reports.generate_feedback(None, PROFILE, INPUTS, j, s))["source"] == "template"


async def test_feedback_too_long_message_rejected():
    j, s = make_judgement()
    long = good_feedback(client_message=" ".join(["word"] * 130))
    llm = FakeLLM(long, good_feedback())
    r = await reports.generate_feedback(llm, PROFILE, INPUTS, j, s)
    assert r["source"] == "gemma" and len(llm.prompts) == 2


async def test_feedback_diet_talk_rejected():
    j, s = make_judgement()
    bad = good_feedback(client_message="Cut your calories and you will lose weight.")
    r = await reports.generate_feedback(FakeLLM(bad, bad), PROFILE, INPUTS, j, s)
    assert r["source"] == "template"


async def test_feedback_pain_adds_stop_and_talk_to_coach():
    j, s = make_judgement(inputs={"pain_during_set": True})
    inputs = {**INPUTS, "pain_during_set": True}
    r = await reports.generate_feedback(FakeLLM(good_feedback()), PROFILE, inputs, j, s)
    msg = r["draft"]["client_message"].lower()
    assert "stop" in msg and "coach" in msg
    assert r["draft"]["coach_only_notes"][0].startswith("PAIN REPORTED")
    # template fallback also follows the rule
    t = await reports.generate_feedback(None, PROFILE, inputs, j, s)
    assert "stop" in t["draft"]["client_message"].lower() and "coach" in t["draft"]["client_message"].lower()


async def test_feedback_pain_rejects_suggestion_to_add_load():
    j, s = make_judgement(inputs={"pain_during_set": True})
    bad = good_feedback(client_message="Stop and see your coach. Then add more weight.")
    llm = FakeLLM(bad, good_feedback())
    r = await reports.generate_feedback(llm, PROFILE, {**INPUTS, "pain_during_set": True}, j, s)
    assert len(llm.prompts) == 2 and r["source"] == "gemma"


async def test_feedback_cue_limit_and_rep_filter_enforced():
    j, s = make_judgement(profile={"experience_level": "beginner"})
    cues = [{"cue": f"cue {i}", "why": "because", "reps": [1, 99]} for i in range(4)]
    r = await reports.generate_feedback(FakeLLM(good_feedback(fix_next_time=cues)),
                                        {**PROFILE, "experience_level": "beginner"}, INPUTS, j, s)
    fixes = r["draft"]["fix_next_time"]
    assert len(fixes) == 2 and all(99 not in c["reps"] for c in fixes)


async def test_llm_payload_has_no_name():
    j, s = make_judgement()
    llm = FakeLLM(good_feedback())
    await reports.generate_feedback(llm, PROFILE, INPUTS, j, s)
    assert "Secret Name" not in llm.prompts[0][1] and "Secret Name" not in llm.prompts[0][0]
    assert reports.profile_for_llm(PROFILE).get("name") is None


def test_invented_numbers_helper():
    payload = {"a": {"angle": 104.3, "reps": [7, 8]}, "t": "form 78"}
    assert reports.invented_numbers(["knee 104 degrees, reps 7 and 8, form 78"], payload) == []
    assert reports.invented_numbers(["knee 90 degrees"], payload) == ["90"]


# ------------------------------------------------------------------ progress
async def test_progress_trend_is_forced_from_code():
    hist = {"sessions": 4, "trend": "improving", "form_scores": [60, 65, 72, 80], "depth_values": [], "relative_loads": []}
    out = {"trend": "declining", "highlights": ["Form score rose from 60 to 80."], "concerns": [],
           "client_message": "Your form is getting better."}
    r = await reports.generate_progress(FakeLLM(out), PROFILE, hist, {"conservative_mode": False})
    assert r["draft"]["trend"] == "improving" and r["source"] == "gemma"


async def test_progress_template_for_little_data():
    hist = {"sessions": 1, "trend": "not_enough_data", "form_scores": [70], "depth_values": [], "relative_loads": []}
    r = await reports.generate_progress(None, PROFILE, hist, {"conservative_mode": False})
    assert r["draft"]["trend"] == "not_enough_data" and "more sessions" in r["draft"]["client_message"]


# ------------------------------------------------------------------ plan
def plan_out(pct=20.0, n=5, exercise="squat"):
    return {"focus": "Build strength", "progression_rule": "Add weight if clean.",
            "coach_review_points": ["Check depth"],
            "sessions": [{"day": d + 1, "exercise": exercise, "sets": 3, "reps": "5", "load_suggestion": "add a lot",
                          "load_change_pct": pct, "tempo": "3-1-1", "cue": "Sit deep"} for d in range(n)]}


RECENT = [{"exercise": "squat", "load_kg": 60, "form_score": 85, "flags": ["shallow_depth"], "pain": False}]


async def test_plan_load_increase_clamped_to_5_percent():
    r = await reports.generate_plan(FakeLLM(plan_out(20)), PROFILE, RECENT, False, [])
    s = r["draft"]["sessions"]
    assert len(s) == 3                                  # trimmed to training_days_per_week
    assert all(x["load_change_pct"] == 5.0 for x in s)
    assert s[0]["load_suggestion"].startswith("63 kg")  # 60 * 1.05 = 63
    assert any("clamped" in w for w in r["warnings"])


async def test_plan_conservative_mode_means_zero_increase():
    r = await reports.generate_plan(FakeLLM(plan_out(10)), {**PROFILE, "age": 70}, RECENT, True, ["Client age is 70."])
    assert all(x["load_change_pct"] == 0.0 for x in r["draft"]["sessions"])
    assert r["draft"]["sessions"][0]["load_suggestion"] == "Stay at 60 kg"
    assert "Client age is 70." in r["draft"]["coach_review_points"]


async def test_plan_recent_pain_forces_zero_increase_and_review_point():
    recent = [{**RECENT[0], "pain": True}]
    r = await reports.generate_plan(FakeLLM(plan_out(5)), PROFILE, recent, False, [])
    assert r["max_load_increase_pct"] == 0.0 and r["conservative_mode"]
    assert all(x["load_change_pct"] <= 0 for x in r["draft"]["sessions"])
    assert "pain" in r["draft"]["coach_review_points"][0].lower()


async def test_plan_deload_is_limited_and_unknown_exercises_removed():
    out = plan_out(-50, n=2)
    out["sessions"].append({**out["sessions"][0], "exercise": "deadlift"})
    r = await reports.generate_plan(FakeLLM(out), PROFILE, RECENT, False, [])
    assert [s["exercise"] for s in r["draft"]["sessions"]] == ["squat", "squat"]
    assert r["draft"]["sessions"][0]["load_change_pct"] == -20.0


async def test_plan_bodyweight_exercise_has_no_kg():
    recent = [{"exercise": "pushup", "load_kg": 0, "form_score": 80, "flags": [], "pain": False}]
    r = await reports.generate_plan(FakeLLM(plan_out(5, n=1, exercise="pushup")), PROFILE, recent, False, [])
    assert "kg" not in r["draft"]["sessions"][0]["load_suggestion"].replace("Bodyweight", "")


async def test_plan_template_when_llm_fails():
    r = await reports.generate_plan(FakeLLM(OllamaError("x")), PROFILE, RECENT, False, [])
    assert r["source"] == "template" and len(r["draft"]["sessions"]) == 3
    WeekPlan.model_validate(r["draft"])
