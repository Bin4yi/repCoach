"""Async client for a local Ollama server (Gemma). Uses structured output via the `format` JSON schema."""
from __future__ import annotations

import json
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .schemas import json_schema

T = TypeVar("T", bound=BaseModel)

TEMPERATURE = 0.3
TIMEOUT_S = 180.0   # local models can be slow on CPU
HTTP_RETRIES = 2    # extra attempts after a network error / timeout / 5xx


class OllamaError(RuntimeError):
    """Ollama is unreachable or kept returning unusable output."""


def pick_model(configured: str, available: list[str]) -> str:
    """Use the configured model if installed, else the newest installed Gemma, else the configured name."""
    if configured in available:
        return configured
    gemmas = [m for m in available if m.lower().startswith("gemma")]
    if gemmas:
        def key(name: str):
            return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", name)]
        return sorted(gemmas, key=key)[-1]
    return configured


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = TIMEOUT_S,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._transport = transport

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self._transport)

    async def health(self) -> dict:
        try:
            async with self._http() as c:
                r = await c.get("/api/tags", timeout=5.0)
                r.raise_for_status()
                names = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "model": self.model, "model_installed": self.model in names, "models": names}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    async def use_best_model(self) -> str:
        """If the configured model is not installed, switch to the newest installed Gemma."""
        h = await self.health()
        if h.get("ok"):
            self.model = pick_model(self.model, h["models"])
        return self.model

    async def _post_chat(self, messages: list[dict], schema: dict) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False, "format": schema,
                   "options": {"temperature": TEMPERATURE}}
        last: Exception | None = None
        for _ in range(HTTP_RETRIES + 1):
            try:
                async with self._http() as c:
                    r = await c.post("/api/chat", json=payload)
                if r.status_code >= 500:
                    raise OllamaError(f"Ollama returned {r.status_code}")
                r.raise_for_status()
                return r.json()["message"]["content"]
            except (httpx.TransportError, httpx.HTTPStatusError, OllamaError, KeyError, ValueError) as exc:
                last = exc
        raise OllamaError(f"Ollama request failed: {last}")

    async def chat_json(self, system: str, user: str, model_cls: type[T]) -> T:
        """Ask for JSON matching `model_cls`. If the reply is not valid, retry ONCE with the error attached."""
        schema = json_schema(model_cls)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        content = await self._post_chat(messages, schema)
        try:
            return model_cls.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That was not valid for the required JSON schema: {str(exc)[:500]}\n"
                                            "Reply again with ONLY valid JSON that matches the schema."},
            ]
        content = await self._post_chat(messages, schema)
        try:
            return model_cls.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise OllamaError(f"Model returned invalid JSON twice: {str(exc)[:200]}") from exc
