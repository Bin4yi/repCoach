"""Coach-only endpoints: login, clients, weekly plans, dashboard data."""
from __future__ import annotations

import hmac
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import services
from ..analysis import progress
from ..analysis.activity import build_activity
from ..db import new_id, new_token, now, serialize
from ..deps import COOKIE_NAME, coach_cookie_value, get_db, require_coach
from ..llm import reports
from ..llm.schemas import WeekPlan
from ..models.schemas import ClientCreate, LoginIn, PlanApproveIn, ProfilePatch

router = APIRouter()


# ------------------------------------------------------------------ auth (MVP: one coach, password from env)
@router.post("/coach/login")
async def login(body: LoginIn, request: Request, response: Response):
    settings = request.app.state.settings
    if not hmac.compare_digest(body.password.encode(), settings.coach_password.encode()):
        raise HTTPException(status_code=401, detail="Wrong password")
    response.set_cookie(COOKIE_NAME, coach_cookie_value(settings.coach_password), httponly=True,
                        samesite="none" if settings.cookie_secure else "lax", secure=settings.cookie_secure,
                        max_age=60 * 60 * 24 * 14)
    return {"ok": True}


@router.post("/coach/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/coach/me", dependencies=[Depends(require_coach)])
async def me(request: Request):
    from ..tts.elevenlabs import enabled
    return {"ok": True, "voice_enabled": enabled(request.app.state.settings)}


# ------------------------------------------------------------------ clients
def _link(request: Request, token: str) -> str:
    return f"{request.app.state.settings.frontend_url.rstrip('/')}/c/{token}"


async def _sessions(db, client_id: str, limit: int = 200) -> list[dict]:
    return await db.sessions.find({"client_id": client_id}).sort("created_at", -1).to_list(length=limit)


@router.post("/coach/clients", dependencies=[Depends(require_coach)], status_code=201)
async def create_client(body: ClientCreate, request: Request, db=Depends(get_db)):
    doc = {"_id": new_id(), "token": new_token(), "name": body.name, "coach_notes": body.coach_notes,
           "profile": {"name": body.name}, "profile_complete": False, "consent_at": None, "created_at": now()}
    await db.clients.insert_one(doc)
    return {"id": doc["_id"], "token": doc["token"], "link": _link(request, doc["token"])}


@router.get("/coach/clients", dependencies=[Depends(require_coach)])
async def list_clients(db=Depends(get_db)):
    clients = await db.clients.find({}).sort("created_at", -1).to_list(length=500)
    all_sessions: dict[str, list[dict]] = {}
    async for s in db.sessions.find({}, {"reps": 0, "ai_feedback": 0}).sort("created_at", -1):
        all_sessions.setdefault(s["client_id"], []).append(s)
    rows = []
    for c in clients:
        ss = all_sessions.get(c["_id"], [])
        ready = [s for s in ss if s["status"] in services.READY and s.get("set")]
        last = ss[0]["created_at"] if ss else None
        rows.append({
            "id": c["_id"], "name": c["name"], "goal": (c.get("profile") or {}).get("goal"),
            "experience_level": (c.get("profile") or {}).get("experience_level"),
            "last_session_at": last, "latest_form_score": ready[0]["set"].get("form_score") if ready else None,
            "trend": services.latest_trend(ss), "session_count": len(ss),
            "warnings": services.warnings_for(c, ss),
        })
    return serialize(rows)


@router.get("/coach/clients/{client_id}", dependencies=[Depends(require_coach)])
async def client_detail(client_id: str, request: Request, db=Depends(get_db)):
    c = await db.clients.find_one({"_id": client_id})
    if not c:
        raise HTTPException(404, "Client not found")
    ss = await _sessions(db, client_id)
    weight = await db.weight_log.find({"client_id": client_id}).sort("date", 1).to_list(length=1000)
    plans = await db.plans.find({"client_id": client_id}).sort("created_at", -1).to_list(length=20)
    ratio = next(((s.get("extras") or {}).get("femur_torso_ratio") for s in ss
                  if s["exercise"] == "squat" and (s.get("extras") or {}).get("femur_torso_ratio")), None)
    profile = c.get("profile") or {}
    return serialize({
        "id": c["_id"], "name": c["name"], "link": _link(request, c["token"]), "profile": profile,
        "profile_complete": c.get("profile_complete", False), "coach_notes": c.get("coach_notes"),
        "consent_at": c.get("consent_at"), "created_at": c["created_at"],
        "derived": {"bmi": services.bmi(profile), "femur_torso_ratio": ratio},
        "warnings": services.warnings_for(c, ss), "trend": services.latest_trend(ss),
        "weight_log": [{"date": w["date"], "kg": w["kg"]} for w in weight],
        "sessions": [services.session_row(s) for s in ss],
        "series": services.build_series(list(reversed(ss))),
        "plans": plans,
    })


@router.patch("/coach/clients/{client_id}", dependencies=[Depends(require_coach)])
async def patch_client(client_id: str, body: ProfilePatch, db=Depends(get_db)):
    c = await db.clients.find_one({"_id": client_id})
    if not c:
        raise HTTPException(404, "Client not found")
    changes = body.model_dump(exclude_unset=True)
    upd: dict = {}
    if "coach_notes" in changes:
        upd["coach_notes"] = changes.pop("coach_notes")
    if "timezone" in changes:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(changes["timezone"])
        except Exception:
            raise HTTPException(422, "Unknown time zone")
    if changes:
        profile = {**(c.get("profile") or {}), **changes}
        upd["profile"] = profile
        if "name" in changes:
            upd["name"] = changes["name"]
        if "body_weight_kg" in changes:
            await db.weight_log.insert_one({"_id": new_id(), "client_id": client_id, "date": now().date().isoformat(),
                                            "kg": changes["body_weight_kg"], "created_at": now()})
    if upd:
        await db.clients.update_one({"_id": client_id}, {"$set": upd})
    return {"ok": True}


@router.get("/coach/clients/{client_id}/activity", dependencies=[Depends(require_coach)])
async def coach_activity(client_id: str, db=Depends(get_db)):
    c = await db.clients.find_one({"_id": client_id})
    if not c:
        raise HTTPException(404, "Client not found")
    return await client_activity(db, c)


async def client_activity(db, c: dict) -> dict:
    ss = await db.sessions.find({"client_id": c["_id"]}, {"reps": 0, "ai_feedback": 0, "signal": 0}).to_list(length=5000)
    p = c.get("profile") or {}
    data = build_activity(ss, tz=services.client_tz(c), training_days_per_week=p.get("training_days_per_week", 3),
                          today=services.today_local(c), client_created=c["created_at"])
    data["profile"] = {"name": c["name"], "goal": p.get("goal"), "experience_level": p.get("experience_level")}
    return serialize(data)


# ------------------------------------------------------------------ weekly plan
@router.post("/coach/clients/{client_id}/plan", dependencies=[Depends(require_coach)], status_code=201)
async def generate_plan(client_id: str, request: Request, db=Depends(get_db)):
    c = await db.clients.find_one({"_id": client_id})
    if not c:
        raise HTTPException(404, "Client not found")
    profile = c.get("profile") or {}
    if not c.get("profile_complete"):
        raise HTTPException(409, "The client has not filled in their profile yet.")
    ss = [s for s in await _sessions(db, client_id, 30) if s["status"] in services.READY and s.get("set")]
    recent = [{"exercise": s["exercise"], "load_kg": (s.get("inputs") or {}).get("load_kg", 0),
               "form_score": s["set"].get("form_score"), "flags": [f["code"] for f in s.get("flags", [])],
               "pain": bool(s["judgement"]["safety"]["pain_reported"])} for s in ss]
    # conservative if the profile says so, or any recent session was conservative
    from ..analysis.judgement import CONSERVATIVE_AGE, injury_relates
    reasons: list[str] = []
    if (profile.get("age") or 0) >= CONSERVATIVE_AGE:
        reasons.append(f"Client age is {profile['age']} (65 or older).")
    if profile.get("goal") == "rehab_return":
        reasons.append("Goal is returning to training after rehab.")
    if profile.get("injuries_or_limits"):
        reasons.append("Injuries or limits are listed: " + profile["injuries_or_limits"])
    result = await reports.generate_plan(request.app.state.llm, profile, recent, bool(reasons), reasons)
    today = services.today_local(c)
    week_start = today + timedelta(days=(7 - today.weekday()))  # next Monday
    doc = {"_id": new_id(), "client_id": client_id, "week_start": week_start.isoformat(), "draft": result["draft"],
           "approved": None, "status": "draft", "source": result["source"], "warnings": result["warnings"],
           "max_load_increase_pct": result["max_load_increase_pct"], "conservative_mode": result["conservative_mode"],
           "last_loads": {r["exercise"]: r["load_kg"] for r in reversed(recent)}, "created_at": now()}
    await db.plans.insert_one(doc)
    return serialize(doc)


@router.post("/plans/{plan_id}/approve", dependencies=[Depends(require_coach)])
async def approve_plan(plan_id: str, body: PlanApproveIn, db=Depends(get_db)):
    p = await db.plans.find_one({"_id": plan_id})
    if not p:
        raise HTTPException(404, "Plan not found")
    plan_dict = body.plan or p["draft"]
    try:
        plan = WeekPlan.model_validate(plan_dict)
    except Exception as exc:
        raise HTTPException(422, f"Plan is not valid: {str(exc)[:200]}")
    client = await db.clients.find_one({"_id": p["client_id"]})
    days = ((client or {}).get("profile") or {}).get("training_days_per_week", 7)
    # code-side rules still apply to coach edits (load cap, supported exercises, sessions per week)
    plan, notes = reports.clamp_plan(plan, p.get("last_loads", {}), p.get("max_load_increase_pct", 5.0), days)
    await db.plans.update_one({"_id": plan_id}, {"$set": {"approved": plan.model_dump(), "status": "approved",
                                                          "approved_at": now(), "approve_notes": notes}})
    return serialize({"ok": True, "plan": plan.model_dump(), "notes": notes})


@router.get("/coach/clients/{client_id}/progress", dependencies=[Depends(require_coach)])
async def progress_overview(client_id: str, db=Depends(get_db)):
    ss = [s for s in await _sessions(db, client_id) if s["status"] in services.READY and s.get("set")]
    pts = [progress.point(s) for s in ss]
    return serialize(progress.history_summary(pts))
