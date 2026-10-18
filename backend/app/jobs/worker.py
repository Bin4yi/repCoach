"""Background processing: a simple in-process asyncio queue (no Celery) + the session processing job."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Awaitable, Callable

from ..analysis import progress
from ..analysis.judgement import build_judgement
from ..db import now
from ..llm import reports

log = logging.getLogger(__name__)
READY_STATUSES = ("ready_for_review", "approved")


class JobQueue:
    """One worker task pulling session ids from an asyncio.Queue. `inline=True` runs jobs immediately (tests)."""

    def __init__(self, handler: Callable[[str], Awaitable[None]], inline: bool = False):
        self.handler = handler
        self.inline = inline
        self._q: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self.inline and self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def submit(self, session_id: str) -> None:
        if self.inline:
            await self.handler(session_id)
        else:
            await self._q.put(session_id)

    async def _run(self) -> None:
        while True:
            sid = await self._q.get()
            try:
                await self.handler(sid)
            except Exception:  # never let one bad job kill the worker
                log.exception("job failed for session %s", sid)
            finally:
                self._q.task_done()


def _delete(path: str | None) -> None:
    if path:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            log.warning("could not delete %s", path)


async def process_session(app_state, session_id: str) -> None:
    """Video -> numbers -> judgement -> Gemma drafts. The raw video is ALWAYS deleted afterwards."""
    db, settings = app_state.db, app_state.settings
    session = await db.sessions.find_one({"_id": session_id})
    if not session:
        return
    video_path = session.get("video_path")
    overlay_path = str(settings.upload_path / "overlays" / f"{session_id}.mp4")
    Path(overlay_path).parent.mkdir(parents=True, exist_ok=True)
    await db.sessions.update_one({"_id": session_id}, {"$set": {"status": "processing", "processing_started_at": now()}})
    try:
        client = await db.clients.find_one({"_id": session["client_id"]})
        profile = client.get("profile") or {}
        inputs = session["inputs"]

        try:
            analysis = await asyncio.to_thread(
                app_state.analyze_video, video_path, inputs["exercise"], inputs["camera_view"],
                profile.get("experience_level", "intermediate"), overlay_path)
        except Exception as exc:
            log.exception("video analysis failed")
            msg = str(exc)
            if "model not found" in msg.lower():
                await db.sessions.update_one({"_id": session_id}, {"$set": {
                    "status": "failed", "error": "The pose model is not installed on the server."}})
            else:
                await db.sessions.update_one({"_id": session_id}, {"$set": {
                    "status": "needs_reshoot", "quality": {
                        "ok": False, "needs_reshoot": True,
                        "reason": "We could not read this video. Please film again and upload an mp4, mov or webm file."}}})
            return

        quality = analysis["quality"]
        if quality["needs_reshoot"]:
            _delete(overlay_path)
            await db.sessions.update_one({"_id": session_id}, {"$set": {"status": "needs_reshoot", "quality": quality}})
            return

        hist_docs = await db.sessions.find({
            "client_id": session["client_id"], "exercise": inputs["exercise"],
            "status": {"$in": list(READY_STATUSES)}, "_id": {"$ne": session_id},
        }).sort("created_at", -1).to_list(length=50)
        history = [progress.point(d) for d in hist_docs]

        judgement = build_judgement(profile, inputs, analysis, quality, history)
        llm = app_state.llm
        feedback = await reports.generate_feedback(llm, profile, inputs, judgement, analysis["set"])
        cur = {"exercise": inputs["exercise"], "form_score": judgement["form_score"],
               "depth": analysis["set"].get("depth_mean"), "relative_load": judgement["relative_load"]}
        prog = await reports.generate_progress(llm, profile, progress.history_summary([cur] + history),
                                               judgement["safety"])

        await db.sessions.update_one({"_id": session_id}, {"$set": {
            "status": "ready_for_review", "quality": quality, "reps": analysis["reps"], "flags": analysis["flags"],
            "set": analysis["set"], "extras": analysis.get("extras", {}), "side": analysis.get("side"),
            "view": analysis.get("view"), "judgement": judgement,
            "ai_feedback": {"draft": feedback["draft"], "source": feedback["source"], "warnings": feedback["warnings"],
                            "progress_draft": prog["draft"], "progress_source": prog["source"],
                            "model": getattr(llm, "model", None)},
            "overlay_available": bool(analysis.get("overlay_written")),
            "overlay_path": overlay_path if analysis.get("overlay_written") else None,
            "processed_at": now(),
        }})
    finally:
        # privacy: the raw video never outlives processing
        _delete(video_path)
        await db.sessions.update_one({"_id": session_id}, {"$set": {"video_path": None, "video_deleted": True}})


async def recover_unfinished(app_state, queue: JobQueue) -> int:
    """After a restart: re-queue sessions whose video still exists, fail the rest."""
    db = app_state.db
    n = 0
    async for s in db.sessions.find({"status": {"$in": ["queued", "processing"]}}):
        p = s.get("video_path")
        if p and os.path.exists(p):
            await db.sessions.update_one({"_id": s["_id"]}, {"$set": {"status": "queued"}})
            await queue.submit(s["_id"])
            n += 1
        else:
            await db.sessions.update_one({"_id": s["_id"]}, {"$set": {
                "status": "failed", "error": "The server restarted before this video was processed. Please upload again."}})
    return n


async def cleanup_overlays(app_state) -> int:
    """Delete overlay videos older than the TTL (they are also deleted when the coach approves)."""
    from datetime import timedelta
    db, settings = app_state.db, app_state.settings
    cutoff = now() - timedelta(days=settings.overlay_ttl_days)
    n = 0
    async for s in db.sessions.find({"overlay_available": True, "created_at": {"$lt": cutoff}}):
        _delete(s.get("overlay_path"))
        await db.sessions.update_one({"_id": s["_id"]}, {"$set": {"overlay_available": False, "overlay_path": None}})
        n += 1
    return n
