"""RepCheck API. `create_app` takes optional overrides so tests can inject a mock DB, LLM and video analyzer."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .db import init_db
from .jobs.worker import JobQueue, cleanup_overlays, process_session, recover_unfinished
from .llm.ollama_client import OllamaClient
from .routers import client_portal, coach, sessions

log = logging.getLogger("repcheck")


def probe_video(path: str) -> float | None:
    """Video length in seconds, or None if OpenCV cannot read it."""
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        cap.release()
        return frames / fps if fps > 0 and frames > 0 else None
    except Exception:
        return None


def create_app(settings: Settings | None = None, *, db=None, llm="auto", analyze_video=None,
               inline_jobs: bool = False) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db = db
        if app.state.db is None:
            app.state.client, app.state.db = await init_db(settings)
        if llm != "auto":
            app.state.llm = llm
        elif settings.llm_provider == "openai":  # DEMO SHIM (revert after the promo video)
            from .llm.openai_client import OpenAIClient
            app.state.llm = OpenAIClient(settings.openai_api_key, settings.openai_model, settings.openai_base_url)
        else:
            app.state.llm = OllamaClient(settings.ollama_url, settings.ollama_model)
        if llm == "auto":
            await app.state.llm.use_best_model()  # fall back to the newest installed Gemma if needed
        if analyze_video is None:
            from .pipeline import analyze_video as default_analyze
            app.state.analyze_video = default_analyze
        else:
            app.state.analyze_video = analyze_video
        app.state.probe_video = probe_video
        app.state.queue = JobQueue(lambda sid: process_session(app.state, sid), inline=inline_jobs)
        await app.state.queue.start()
        await recover_unfinished(app.state, app.state.queue)
        await cleanup_overlays(app.state)
        if settings.demo_seed_on_start:
            from scripts.seed_demo_data import seed
            await seed(app.state.db, reset=False)
        yield
        await app.state.queue.stop()

    app = FastAPI(title="RepCheck API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(coach.router)
    app.include_router(client_portal.router)
    app.include_router(sessions.router)

    @app.get("/health")
    async def health():
        from .tts.elevenlabs import enabled
        mongo = {"ok": False}
        try:
            await app.state.db.command("ping")
            mongo = {"ok": True}
        except Exception as exc:
            mongo = {"ok": False, "error": str(exc)[:120]}
        ollama = await app.state.llm.health() if hasattr(app.state.llm, "health") else {"ok": app.state.llm is not None}
        return {"status": "ok" if mongo["ok"] and ollama.get("ok") else "degraded", "mongo": mongo,
                "ollama": ollama, "voice_enabled": enabled(settings)}

    return app


app = create_app()
