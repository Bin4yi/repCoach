"""API tests against an in-memory Mongo (mongomock) with a fake LLM and fake video analyzer."""
import httpx

from app.pose import synthetic as syn
from tests.conftest import upload


# ------------------------------------------------------------------ health & auth
def test_health(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["mongo"]["ok"] and h["ollama"]["ok"] and h["voice_enabled"] is False


def test_health_degraded_when_ollama_down(client, llm):
    llm.down = True
    assert client.get("/health").json()["status"] == "degraded"


def test_coach_endpoints_need_login(client):
    for method, url in [("get", "/coach/clients"), ("post", "/coach/clients"), ("get", "/coach/clients/x"),
                        ("get", "/sessions/x"), ("post", "/plans/x/approve"), ("get", "/coach/clients/x/activity")]:
        assert getattr(client, method)(url).status_code == 401, url


def test_login(client):
    assert client.post("/coach/login", json={"password": "nope"}).status_code == 401
    assert client.post("/coach/login", json={"password": "secret-pw"}).status_code == 200
    assert client.get("/coach/clients").status_code == 200
    client.post("/coach/logout")
    assert client.get("/coach/clients").status_code == 401


def test_forged_cookie_rejected(client):
    client.cookies.set("repcheck_coach", "abc")
    assert client.get("/coach/clients").status_code == 401


# ------------------------------------------------------------------ client onboarding
def test_create_client_and_token_link(coach):
    r = coach.post("/coach/clients", json={"name": "Sam"}).json()
    assert len(r["token"]) >= 30 and r["link"] == f"http://localhost:3000/c/{r['token']}"
    home = coach.get(f"/c/{r['token']}").json()
    assert home["profile_complete"] is False and home["reports"] == []
    assert coach.get("/c/not-a-token").status_code == 404


def test_profile_needs_consent_and_validates(coach, profile):
    tok = coach.post("/coach/clients", json={"name": "Sam"}).json()["token"]
    assert coach.put(f"/c/{tok}/profile", json={**profile, "consent": False}).status_code == 422
    assert coach.put(f"/c/{tok}/profile", json={**profile, "age": 12}).status_code == 422
    assert coach.put(f"/c/{tok}/profile", json={**profile, "goal": "bulk"}).status_code == 422
    assert coach.put(f"/c/{tok}/profile", json={**profile, "timezone": "Mars/Base"}).status_code == 422
    assert coach.put(f"/c/{tok}/profile", json=profile).status_code == 200
    home = coach.get(f"/c/{tok}").json()
    assert home["profile_complete"] and home["consented"] and home["profile"]["goal"] == "strength"
    assert home["weight_log"][0]["kg"] == 62
    # editing later does not need consent again
    assert coach.put(f"/c/{tok}/profile", json={**profile, "consent": False, "body_weight_kg": 61}).status_code == 200


def test_upload_requires_profile_and_consent(coach):
    tok = coach.post("/coach/clients", json={"name": "Sam"}).json()["token"]
    assert upload(coach, tok).status_code == 403


def test_coach_notes_never_reach_the_client(coach, ready_client):
    cid, tok = ready_client
    assert coach.patch(f"/coach/clients/{cid}", json={"coach_notes": "secretly nervous"}).status_code == 200
    assert "nervous" not in coach.get(f"/c/{tok}").text
    assert coach.get(f"/coach/clients/{cid}").json()["coach_notes"] == "secretly nervous"
    d = coach.get(f"/coach/clients/{cid}").json()
    assert d["derived"]["bmi"]["value"] == 22.8 and "rough" in d["derived"]["bmi"]["note"]
    assert "bmi" not in coach.get(f"/c/{tok}").text.lower()


def test_coach_patch_profile_logs_weight(coach, ready_client):
    cid, _ = ready_client
    coach.patch(f"/coach/clients/{cid}", json={"body_weight_kg": 60.5, "injuries_or_limits": "left knee pain"})
    d = coach.get(f"/coach/clients/{cid}").json()
    assert d["profile"]["injuries_or_limits"] == "left knee pain" and d["weight_log"][-1]["kg"] == 60.5


# ------------------------------------------------------------------ upload validation
def test_upload_rejects_bad_files(coach, ready_client):
    _, tok = ready_client
    r = coach.post(f"/c/{tok}/videos", data={"exercise": "squat", "camera_view": "side"},
                   files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    big = coach.post(f"/c/{tok}/videos", data={"exercise": "squat", "camera_view": "side"},
                     files={"file": ("x.mp4", b"0" * (1024 * 1024 + 10), "video/mp4")})
    assert big.status_code == 413
    assert upload(coach, tok, exercise="deadlift").status_code == 422
    assert upload(coach, tok, rpe=11).status_code == 422
    coach.app_state.probe_video = lambda p: 75.0
    assert upload(coach, tok).status_code == 413
    folder = coach.app_state.settings.upload_path / "videos"
    assert not folder.exists() or list(folder.iterdir()) == []   # rejected files are not kept


# ------------------------------------------------------------------ full flow
def test_upload_process_review_approve_flow(coach, ready_client):
    cid, tok = ready_client
    r = upload(coach, tok, client_comment="felt ok")
    assert r.status_code == 201
    sid = r.json()["session_id"]

    s = coach.get(f"/sessions/{sid}").json()
    assert s["status"] == "ready_for_review" and s["client"]["name"] == "Asha Perera"
    assert s["set"]["rep_count"] == 5 and 0 <= s["judgement"]["form_score"] <= 100
    assert s["judgement"]["flags"][0]["code"] == "shallow_depth"
    assert s["judgement"]["relative_load"] == round(60 / 62, 2)
    assert len(s["reps"]) == 5 and s["ai_feedback"]["source"] == "gemma"
    assert s["ai_feedback"]["draft"]["client_message"].startswith("Good work")
    assert s["ai_feedback"]["progress_draft"]["trend"] == "not_enough_data"
    assert "video_path" not in s and s["video_deleted"] is True
    # raw video is gone from disk
    vids = coach.app_state.settings.upload_path / "videos"
    assert list(vids.iterdir()) == []

    # not visible to the client before approval
    assert coach.get(f"/c/{tok}").json()["reports"] == []
    assert coach.get(f"/c/{tok}/activity").json()["totals"]["sessions"] == 1

    # approve with an edited message
    bad = coach.post(f"/sessions/{sid}/approve", json={"client_message": ""})
    assert bad.status_code == 422
    ok = coach.post(f"/sessions/{sid}/approve", json={"client_message": "Edited by coach: nice depth work!"})
    assert ok.status_code == 200
    reports = coach.get(f"/c/{tok}").json()["reports"]
    assert len(reports) == 1 and reports[0]["message"] == "Edited by coach: nice depth work!"
    assert "judgement" not in reports[0]
    assert coach.get(f"/sessions/{sid}").json()["status"] == "approved"
    feed = [i["text"] for g in coach.get(f"/c/{tok}/activity").json()["feed"] for i in g["items"]]
    assert "Coach approved your report" in feed


def test_overlay_available_until_approved(coach, ready_client, scenario):
    _, tok = ready_client
    scenario.write_overlay = True
    sid = upload(coach, tok).json()["session_id"]
    assert coach.get(f"/sessions/{sid}").json()["overlay_available"] is True
    r = coach.get(f"/sessions/{sid}/overlay.mp4")
    assert r.status_code == 200 and r.content == b"fake-mp4"
    path = coach.app_state.settings.upload_path / "overlays" / f"{sid}.mp4"
    assert path.exists()
    coach.post(f"/sessions/{sid}/approve", json={"client_message": "ok"})
    assert not path.exists()
    assert coach.get(f"/sessions/{sid}/overlay.mp4").status_code == 404
    assert coach.get(f"/sessions/{sid}").json()["overlay_available"] is False


def test_old_overlays_are_cleaned_up(coach, ready_client, scenario):
    import asyncio
    from datetime import timedelta
    from app.db import now
    from app.jobs.worker import cleanup_overlays
    _, tok = ready_client
    scenario.write_overlay = True
    sid = upload(coach, tok).json()["session_id"]
    path = coach.app_state.settings.upload_path / "overlays" / f"{sid}.mp4"
    db = coach.app_state.db

    async def run():
        await db.sessions.update_one({"_id": sid}, {"$set": {"created_at": now() - timedelta(days=8)}})
        return await cleanup_overlays(coach.app_state)

    assert asyncio.new_event_loop().run_until_complete(run()) == 1
    assert not path.exists()


def test_overlay_404_when_missing(coach, ready_client):
    _, tok = ready_client
    sid = upload(coach, tok).json()["session_id"]
    assert coach.get(f"/sessions/{sid}/overlay.mp4").status_code == 404


def test_approve_before_ready_is_rejected(coach, ready_client, scenario):
    _, tok = ready_client
    scenario.make = lambda: syn.gen_squat_front()          # wrong camera -> needs reshoot
    sid = upload(coach, tok).json()["session_id"]
    assert coach.post(f"/sessions/{sid}/approve", json={"client_message": "x"}).status_code == 409


# ------------------------------------------------------------------ reshoot / failure
def test_needs_reshoot_is_friendly(coach, ready_client, scenario):
    cid, tok = ready_client
    scenario.make = lambda: syn.gen_squat_front()
    sid = upload(coach, tok).json()["session_id"]
    s = coach.get(f"/sessions/{sid}").json()
    assert s["status"] == "needs_reshoot" and "side" in s["quality"]["reason"]
    assert s.get("ai_feedback") is None
    home = coach.get(f"/c/{tok}").json()
    assert "side" in home["reshoot_reason"]
    rows = {r["id"]: r for r in coach.get("/coach/clients").json()}
    assert any(w["code"] == "needs_reshoot" for w in rows[cid]["warnings"])
    assert coach.get(f"/c/{tok}/activity").json()["totals"]["sessions"] == 0   # reshoots don't count


def test_unreadable_video_becomes_reshoot(coach, ready_client, scenario):
    _, tok = ready_client
    scenario.error = ValueError("Could not open the video file.")
    sid = upload(coach, tok).json()["session_id"]
    s = coach.get(f"/sessions/{sid}").json()
    assert s["status"] == "needs_reshoot" and "could not read" in s["quality"]["reason"]
    assert coach.app_state.settings.upload_path.joinpath("videos").exists()
    assert list(coach.app_state.settings.upload_path.joinpath("videos").iterdir()) == []   # video deleted anyway


def test_missing_pose_model_marks_failed(coach, ready_client, scenario):
    _, tok = ready_client
    scenario.error = RuntimeError("Pose model not found at x")
    sid = upload(coach, tok).json()["session_id"]
    assert coach.get(f"/sessions/{sid}").json()["status"] == "failed"


# ------------------------------------------------------------------ safety through the API
def test_pain_flow(coach, ready_client, llm):
    cid, tok = ready_client
    sid = upload(coach, tok, pain_during_set="true", pain_text="sharp pain right knee").json()["session_id"]
    s = coach.get(f"/sessions/{sid}").json()
    assert s["judgement"]["safety"]["pain_reported"] and s["judgement"]["safety"]["conservative_mode"]
    assert s["judgement"]["max_load_increase_pct"] == 0.0
    msg = s["ai_feedback"]["draft"]["client_message"].lower()
    assert "stop" in msg and "coach" in msg
    assert s["ai_feedback"]["draft"]["coach_only_notes"][0].startswith("PAIN REPORTED")
    row = next(r for r in coach.get("/coach/clients").json() if r["id"] == cid)
    assert any(w["code"] == "pain" and w["level"] == "red" for w in row["warnings"])
    # a plan made after pain must not raise load
    plan = coach.post(f"/coach/clients/{cid}/plan").json()
    assert plan["conservative_mode"] and all(x["load_change_pct"] <= 0 for x in plan["draft"]["sessions"])
    assert "pain" in plan["draft"]["coach_review_points"][0].lower()


def test_ollama_down_uses_template_fallback(coach, ready_client, llm):
    llm.down = True
    _, tok = ready_client
    sid = upload(coach, tok).json()["session_id"]
    s = coach.get(f"/sessions/{sid}").json()
    assert s["status"] == "ready_for_review" and s["ai_feedback"]["source"] == "template"
    assert "deeper" in s["ai_feedback"]["draft"]["client_message"].lower()


def test_body_weight_today_updates_log_and_relative_load(coach, ready_client):
    cid, tok = ready_client
    sid = upload(coach, tok, body_weight_today_kg=60, load_kg=60).json()["session_id"]
    assert coach.get(f"/sessions/{sid}").json()["judgement"]["relative_load"] == 1.0
    assert coach.get(f"/coach/clients/{cid}").json()["weight_log"][-1]["kg"] == 60


# ------------------------------------------------------------------ plans
def test_plan_generate_clamp_and_approve(coach, ready_client):
    cid, tok = ready_client
    upload(coach, tok, load_kg=80)
    plan = coach.post(f"/coach/clients/{cid}/plan")
    assert plan.status_code == 201
    p = plan.json()
    assert p["status"] == "draft" and len(p["draft"]["sessions"]) == 3
    assert all(s["load_change_pct"] == 5.0 for s in p["draft"]["sessions"])      # LLM said 15, code clamps
    assert p["draft"]["sessions"][0]["load_suggestion"].startswith("84 kg")
    assert coach.get(f"/c/{tok}").json()["plan"] is None                       # not visible before approval

    edited = {**p["draft"], "focus": "Coach edited focus"}
    edited["sessions"][0]["load_change_pct"] = 40.0                             # coach edits are re-clamped
    ok = coach.post(f"/plans/{p['id']}/approve", json={"plan": edited}).json()
    assert ok["plan"]["focus"] == "Coach edited focus" and ok["plan"]["sessions"][0]["load_change_pct"] == 5.0
    home = coach.get(f"/c/{tok}").json()
    assert home["plan"]["focus"] == "Coach edited focus" and home["plan_week_start"]
    assert coach.post("/plans/nope/approve", json={}).status_code == 404
    assert coach.post(f"/plans/{p['id']}/approve", json={"plan": {"focus": 1}}).status_code == 422


def test_plan_needs_profile(coach):
    cid = coach.post("/coach/clients", json={"name": "Sam"}).json()["id"]
    assert coach.post(f"/coach/clients/{cid}/plan").status_code == 409


def test_older_client_plan_is_conservative(coach, profile):
    r = coach.post("/coach/clients", json={"name": "Old"}).json()
    coach.put(f"/c/{r['token']}/profile", json={**profile, "age": 67, "goal": "rehab_return",
                                                "injuries_or_limits": "knee replacement"})
    plan = coach.post(f"/coach/clients/{r['id']}/plan").json()
    assert plan["conservative_mode"] and plan["max_load_increase_pct"] == 0.0
    assert any("65" in x or "rehab" in x for x in plan["draft"]["coach_review_points"])


# ------------------------------------------------------------------ dashboard data
def test_dashboard_and_client_detail(coach, ready_client):
    cid, tok = ready_client
    for _ in range(3):
        upload(coach, tok)
    rows = coach.get("/coach/clients").json()
    row = next(r for r in rows if r["id"] == cid)
    assert row["latest_form_score"] is not None and row["session_count"] == 3
    assert any(w["code"] == "pending_review" for w in row["warnings"])
    d = coach.get(f"/coach/clients/{cid}").json()
    assert len(d["sessions"]) == 3 and len(d["series"]["squat"]) == 3
    assert d["series"]["squat"][0]["relative_load"] == round(60 / 62, 2)
    a = coach.get(f"/coach/clients/{cid}/activity").json()
    assert a["totals"]["sessions"] == 3 and a["days"][-1]["points"] > 0 and a["profile"]["name"] == "Asha Perera"
    assert coach.get("/coach/clients/nope").status_code == 404


def test_no_upload_warning_for_stale_client(coach, ready_client):
    import asyncio
    from datetime import timedelta
    from app.db import now
    cid, _ = ready_client
    db = coach.app_state.db

    async def age():
        await db.clients.update_one({"_id": cid}, {"$set": {"created_at": now() - timedelta(days=30)}})

    asyncio.new_event_loop().run_until_complete(age())
    row = next(r for r in coach.get("/coach/clients").json() if r["id"] == cid)
    assert any(w["code"] == "no_upload" for w in row["warnings"])


# ------------------------------------------------------------------ voice note
def test_voice_disabled_without_key(coach, ready_client):
    _, tok = ready_client
    sid = upload(coach, tok).json()["session_id"]
    assert coach.post(f"/sessions/{sid}/voice", json={"text": "hi"}).status_code == 501
    assert coach.get("/coach/me").json()["voice_enabled"] is False


def test_voice_with_key_uses_elevenlabs(coach, ready_client):
    _, tok = ready_client
    sid = upload(coach, tok).json()["session_id"]
    coach.app_state.settings.elevenlabs_api_key = "k"
    seen = {}

    def handler(request: httpx.Request):
        seen["key"] = request.headers["xi-api-key"]
        seen["body"] = request.content
        return httpx.Response(200, content=b"ID3audio")

    coach.app_state.tts_transport = httpx.MockTransport(handler)
    assert coach.post(f"/sessions/{sid}/voice", json={}).status_code == 409      # nothing approved yet
    r = coach.post(f"/sessions/{sid}/voice", json={"text": "Great work"})
    assert r.status_code == 200 and r.content == b"ID3audio" and r.headers["content-type"] == "audio/mpeg"
    assert seen["key"] == "k" and b"Great work" in seen["body"]
    assert coach.get("/coach/me").json()["voice_enabled"] is True
