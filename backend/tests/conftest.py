"""Shared fixtures: app with in-memory Mongo, a fake LLM and a fake video analyzer (synthetic skeletons)."""
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.config import Settings
from app.llm.schemas import ProgressSummary, SessionFeedback, WeekPlan
from app.main import create_app
from app.pipeline import analyze_sequence
from app.pose import synthetic as syn


class FakeLLM:
    """Answers each task with a canned valid JSON; flip `down` to simulate Ollama being offline."""
    model = "fake-gemma"

    def __init__(self):
        self.down = False
        self.calls = []

    async def health(self):
        return {"ok": not self.down, "model": self.model}

    async def chat_json(self, system, user, model_cls):
        from app.llm.ollama_client import OllamaError
        self.calls.append(model_cls.__name__)
        if self.down:
            raise OllamaError("offline")
        if model_cls is SessionFeedback:
            return SessionFeedback(summary="Solid squat set.", what_went_well=["Steady tempo."],
                                   fix_next_time=[{"cue": "Sit a little deeper", "why": "Depth was short.", "reps": [1]}],
                                   coach_only_notes=[], client_message="Good work! Try to sit a little deeper next time.")
        if model_cls is ProgressSummary:
            return ProgressSummary(trend="stable", highlights=[], concerns=[],
                                   client_message="Your form is steady. Keep it up.")
        if model_cls is WeekPlan:
            return WeekPlan.model_validate({
                "focus": "Build depth", "progression_rule": "Add load when clean.", "coach_review_points": [],
                "sessions": [{"day": d, "exercise": "squat", "sets": 3, "reps": "6-8", "load_suggestion": "add",
                              "load_change_pct": 15.0, "tempo": "3-1-1", "cue": "Sit deep"} for d in (1, 3, 5)]})
        raise AssertionError(model_cls)


class Scenario:
    """What the fake video analyzer should 'see' for the next upload."""
    def __init__(self):
        self.make = lambda: syn.gen_squat(min_knee=105)
        self.error: Exception | None = None
        self.view = "side"
        self.write_overlay = False


@pytest.fixture
def scenario():
    return Scenario()


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def settings(tmp_path):
    return Settings(mongodb_uri="mongomock://", coach_password="secret-pw", upload_dir=str(tmp_path / "uploads"),
                    frontend_url="http://localhost:3000", max_upload_mb=1, elevenlabs_api_key="")


@pytest.fixture
def client(settings, llm, scenario):
    def fake_analyze(path, exercise, view, experience, overlay_path):
        if scenario.error:
            raise scenario.error
        out = analyze_sequence(scenario.make(), exercise, scenario.view or view, experience)
        out["overlay_written"] = False
        if scenario.write_overlay and out["reps"]:
            with open(overlay_path, "wb") as f:
                f.write(b"fake-mp4")
            out["overlay_written"] = True
        return out

    db = AsyncMongoMockClient(tz_aware=True)["repcheck_test"]
    app = create_app(settings, db=db, llm=llm, analyze_video=fake_analyze, inline_jobs=True)
    with TestClient(app) as c:
        app.state.probe_video = lambda p: 12.0
        c.app_state = app.state
        yield c


@pytest.fixture
def coach(client):
    r = client.post("/coach/login", json={"password": "secret-pw"})
    assert r.status_code == 200
    return client


PROFILE = {"name": "Asha Perera", "age": 31, "sex": "female", "height_cm": 165, "body_weight_kg": 62,
           "experience_level": "intermediate", "goal": "strength", "training_days_per_week": 3,
           "injuries_or_limits": None, "equipment": ["barbell"], "timezone": "Asia/Colombo", "consent": True}


@pytest.fixture
def profile():
    return dict(PROFILE)


@pytest.fixture
def ready_client(coach, profile):
    """A coach-created client with a completed profile. Returns (id, token)."""
    r = coach.post("/coach/clients", json={"name": "Asha Perera"})
    assert r.status_code == 201
    cid, token = r.json()["id"], r.json()["token"]
    assert coach.put(f"/c/{token}/profile", json=profile).status_code == 200
    return cid, token


def upload(client, token, **over):
    data = {"exercise": "squat", "camera_view": "side", "load_kg": "60", "rpe": "7", "sets_done_today": "3"}
    data.update({k: str(v) for k, v in over.items()})
    return client.post(f"/c/{token}/videos", data=data, files={"file": ("set.mp4", b"\x00\x00fakevideo", "video/mp4")})
