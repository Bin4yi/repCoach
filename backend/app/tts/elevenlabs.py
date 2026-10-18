"""Optional ElevenLabs text-to-speech for a coach voice note. Disabled unless ELEVENLABS_API_KEY is set."""
from __future__ import annotations

import httpx

API = "https://api.elevenlabs.io/v1/text-to-speech"
MAX_CHARS = 1500


class TTSDisabled(RuntimeError):
    pass


def enabled(settings) -> bool:
    return bool(settings.elevenlabs_api_key)


async def synthesize(settings, text: str, transport: httpx.AsyncBaseTransport | None = None) -> bytes:
    """Return MP3 bytes for `text` (the coach-approved message)."""
    if not enabled(settings):
        raise TTSDisabled("ElevenLabs is not configured")
    text = text.strip()[:MAX_CHARS]
    async with httpx.AsyncClient(timeout=60, transport=transport) as c:
        r = await c.post(f"{API}/{settings.elevenlabs_voice_id}",
                         headers={"xi-api-key": settings.elevenlabs_api_key, "accept": "audio/mpeg"},
                         json={"text": text, "model_id": "eleven_multilingual_v2"})
        r.raise_for_status()
        return r.content
