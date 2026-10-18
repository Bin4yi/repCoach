"""Client-facing endpoints, secured only by the private link token (MVP limit, see DECISIONS.md)."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from .. import services
from ..db import new_id, now, serialize
from ..deps import client_by_token, get_db
from ..models.schemas import ProfileIn, VideoInputs
from .coach import client_activity

log = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXT = {".mp4", ".mov", ".webm"}
CHUNK = 1024 * 1024


async def _log_weight(db, client_id: str, kg: float, tz_date: str) -> None:
    await db.weight_log.insert_one({"_id": new_id(), "client_id": client_id, "date": tz_date, "kg": kg,
                                    "created_at": now()})


@router.get("/c/{token}")
async def client_home(client: dict = Depends(client_by_token), db=Depends(get_db)):
    """Profile + only coach-approved reports/plans."""
    ss = await db.sessions.find({"client_id": client["_id"], "status": "approved"}).sort("created_at", -1).to_list(100)
    reports_ = []
    for s in ss:
        a = s.get("approved") or {}
        reports_.append({"id": s["_id"], "exercise": s["exercise"], "created_at": s["created_at"],
                         "form_score": (s.get("set") or {}).get("form_score"),
                         "rep_count": (s.get("set") or {}).get("rep_count"),
                         "message": a.get("client_message"), "progress_message": a.get("progress_message"),
                         "approved_at": a.get("approved_at")})
    plan = await db.plans.find_one({"client_id": client["_id"], "status": "approved"}, sort=[("approved_at", -1)])
    weight = await db.weight_log.find({"client_id": client["_id"]}).sort("date", 1).to_list(500)
    pending = await db.sessions.count_documents({"client_id": client["_id"],
                                                 "status": {"$in": ["queued", "processing", "ready_for_review"]}})
    reshoot = await db.sessions.find_one({"client_id": client["_id"], "status": "needs_reshoot"}, sort=[("created_at", -1)])
    latest = await db.sessions.find_one({"client_id": client["_id"]}, sort=[("created_at", -1)])
    return serialize({
        "name": client["name"], "profile": services.client_safe_profile(client),
        "profile_complete": client.get("profile_complete", False), "consented": bool(client.get("consent_at")),
        "reports": reports_, "plan": plan["approved"] if plan else None,
        "plan_week_start": plan["week_start"] if plan else None,
        "weight_log": [{"date": w["date"], "kg": w["kg"]} for w in weight],
        "pending_count": pending,
        "reshoot_reason": (reshoot.get("quality") or {}).get("reason") if reshoot and latest and latest["_id"] == reshoot["_id"] else None,
    })


@router.put("/c/{token}/profile")
async def put_profile(body: ProfileIn, client: dict = Depends(client_by_token), db=Depends(get_db)):
    if not body.consent and not client.get("consent_at"):
        raise HTTPException(422, "Please read and accept the privacy note before continuing.")
    profile = body.model_dump(exclude={"consent"})
    old = client.get("profile") or {}
    upd = {"profile": profile, "name": body.name, "profile_complete": True}
    if not client.get("consent_at"):
        upd["consent_at"] = now()
    await db.clients.update_one({"_id": client["_id"]}, {"$set": upd})
    if old.get("body_weight_kg") != body.body_weight_kg:
        await _log_weight(db, client["_id"], body.body_weight_kg, services.today_local({"profile": profile}).isoformat())
    return {"ok": True}


@router.get("/c/{token}/activity")
async def activity(client: dict = Depends(client_by_token), db=Depends(get_db)):
    return await client_activity(db, client)


@router.post("/c/{token}/videos", status_code=201)
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    exercise: str = Form(...),
    camera_view: str = Form(...),
    load_kg: float = Form(0),
    target_reps: Optional[int] = Form(None),
    sets_done_today: Optional[int] = Form(None),
    rpe: Optional[int] = Form(None),
    pain_during_set: bool = Form(False),
    pain_text: Optional[str] = Form(None),
    body_weight_today_kg: Optional[float] = Form(None),
    client_comment: Optional[str] = Form(None),
    client: dict = Depends(client_by_token),
    db=Depends(get_db),
):
    state = request.app.state
    settings = state.settings
    if not client.get("profile_complete") or not client.get("consent_at"):
        raise HTTPException(403, "Please fill in your profile and accept the privacy note first.")
    try:
        inputs = VideoInputs(exercise=exercise, camera_view=camera_view, load_kg=load_kg, target_reps=target_reps,
                             sets_done_today=sets_done_today, rpe=rpe, pain_during_set=pain_during_set,
                             pain_text=pain_text, body_weight_today_kg=body_weight_today_kg,
                             client_comment=client_comment)
    except Exception as exc:
        raise HTTPException(422, f"Check the form: {str(exc)[:300]}")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, "Please upload an mp4, mov or webm video.")

    session_id = new_id()
    folder = settings.upload_path / "videos"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session_id}{ext}"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with open(path, "wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"The video is too big. The limit is {settings.max_upload_mb} MB.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "The file is empty.")
        duration = await _probe(state, str(path))
        if duration is not None and duration > settings.max_video_seconds + 0.5:
            raise HTTPException(413, f"The video is too long. Please keep it under {settings.max_video_seconds} seconds.")
    except HTTPException:
        path.unlink(missing_ok=True)
        raise

    doc = {"_id": session_id, "client_id": client["_id"], "exercise": inputs.exercise, "inputs": inputs.model_dump(),
           "status": "queued", "video_path": str(path), "created_at": now()}
    await db.sessions.insert_one(doc)
    if inputs.body_weight_today_kg:
        await _log_weight(db, client["_id"], inputs.body_weight_today_kg, services.today_local(client).isoformat())
        await db.clients.update_one({"_id": client["_id"]}, {"$set": {"profile.body_weight_kg": inputs.body_weight_today_kg}})
    await state.queue.submit(session_id)
    return {"session_id": session_id, "status": "queued"}


async def _probe(state, path: str) -> float | None:
    import asyncio
    return await asyncio.to_thread(state.probe_video, path)
