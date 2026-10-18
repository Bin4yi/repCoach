"""Session review endpoints (coach only): status, metrics, overlay video, approve, voice note."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..db import now, serialize
from ..deps import get_db, require_coach
from ..models.schemas import ApproveIn
from ..tts import elevenlabs

router = APIRouter(dependencies=[Depends(require_coach)])

HIDDEN = {"video_path", "overlay_path", "signal"}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db=Depends(get_db)):
    s = await db.sessions.find_one({"_id": session_id})
    if not s:
        raise HTTPException(404, "Session not found")
    client = await db.clients.find_one({"_id": s["client_id"]}) or {}
    out = {k: v for k, v in s.items() if k not in HIDDEN}
    p = client.get("profile") or {}
    out["client"] = {"id": client.get("_id"), "name": client.get("name"), "goal": p.get("goal"),
                     "experience_level": p.get("experience_level"), "age": p.get("age"),
                     "injuries_or_limits": p.get("injuries_or_limits")}
    out["overlay_available"] = bool(s.get("overlay_available") and s.get("overlay_path") and os.path.exists(s["overlay_path"]))
    return serialize(out)


@router.get("/sessions/{session_id}/overlay.mp4")
async def overlay(session_id: str, db=Depends(get_db)):
    s = await db.sessions.find_one({"_id": session_id})
    path = s.get("overlay_path") if s else None
    if not path or not os.path.exists(path):
        raise HTTPException(404, "The overlay video is no longer available.")
    return FileResponse(path, media_type="video/mp4")


@router.post("/sessions/{session_id}/approve")
async def approve(session_id: str, body: ApproveIn, db=Depends(get_db)):
    s = await db.sessions.find_one({"_id": session_id})
    if not s:
        raise HTTPException(404, "Session not found")
    if s["status"] not in ("ready_for_review", "approved"):
        raise HTTPException(409, f"This session is '{s['status']}' and cannot be approved yet.")
    approved = {"client_message": body.client_message.strip(),
                "progress_message": (body.progress_message or "").strip() or None,
                "coach_note": body.coach_note, "approved_at": now()}
    # the overlay is only kept until the coach has reviewed the session
    if s.get("overlay_path"):
        try:
            os.remove(s["overlay_path"])
        except OSError:
            pass
    await db.sessions.update_one({"_id": session_id}, {"$set": {
        "status": "approved", "approved": approved, "approved_at": approved["approved_at"],
        "overlay_available": False, "overlay_path": None}})
    return serialize({"ok": True, "approved": approved})


class VoiceIn(BaseModel):
    text: Optional[str] = None


@router.post("/sessions/{session_id}/voice")
async def voice(session_id: str, request: Request, body: VoiceIn | None = None, db=Depends(get_db)):
    settings = request.app.state.settings
    if not elevenlabs.enabled(settings):
        raise HTTPException(501, "Voice notes are not set up (no ElevenLabs key).")
    s = await db.sessions.find_one({"_id": session_id})
    if not s:
        raise HTTPException(404, "Session not found")
    text = (body.text if body and body.text else None) or (s.get("approved") or {}).get("client_message")
    if not text:
        raise HTTPException(409, "Approve a message first, or send the text to speak.")
    try:
        audio = await elevenlabs.synthesize(settings, text, transport=getattr(request.app.state, "tts_transport", None))
    except Exception as exc:
        raise HTTPException(502, f"Voice service error: {str(exc)[:120]}")
    return Response(content=audio, media_type="audio/mpeg")
