"""DEMO SHIM: an OpenAI-compatible stand-in for the Ollama client, used only to record the promo video.

It has the same interface as OllamaClient (`health`, `use_best_model`, `chat_json`) and raises OllamaError on
failure, so the report generators, safety checks and template fallbacks behave exactly the same.
Select it with LLM_PROVIDER=openai and OPENAI_API_KEY. The product itself runs Gemma via Ollama.
"""
from __future__ import annotations

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .ollama_client import HTTP_RETRIES, TEMPERATURE, TIMEOUT_S, OllamaError
from .schemas import json_schema

T = TypeVar("T", bound=BaseModel)


class OpenAIClient:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1",
                 timeout: float = TIMEOUT_S, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self._transport,
                                 headers={"Authorization": f"Bearer {self.api_key}"})

    async def health(self) -> dict:
        if not self.api_key:
            return {"ok": False, "error": "OPENAI_API_KEY is not set"}
        try:
            async with self._http() as c:
                r = await c.get("/models", timeout=10.0)
                r.raise_for_status()
            return {"ok": True, "model": self.model, "provider": "openai (demo shim)"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    async def use_best_model(self) -> str:
        return self.model

    async def _post(self, messages: list[dict]) -> str:
        payload = {"model": self.model, "messages": messages, "temperature": TEMPERATURE,
                   "response_format": {"type": "json_object"}}
        last: Exception | None = None
        for _ in range(HTTP_RETRIES + 1):
            try:
                async with self._http() as c:
                    r = await c.post("/chat/completions", json=payload)
                if r.status_code >= 500 or r.status_code == 429:
                    raise OllamaError(f"OpenAI returned {r.status_code}")
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except (httpx.TransportError, httpx.HTTPStatusError, OllamaError, KeyError, ValueError) as exc:
                last = exc
        raise OllamaError(f"OpenAI request failed: {last}")

    async def chat_json(self, system: str, user: str, model_cls: type[T]) -> T:
        """Same contract as OllamaClient.chat_json: JSON matching the schema, one retry with the error attached."""
        schema = json.dumps(json_schema(model_cls))
        messages = [
            {"role": "system", "content": f"{system}\n\nReply with a single JSON object matching this JSON schema:\n{schema}"},
            {"role": "user", "content": user},
        ]
        content = await self._post(messages)
        try:
            return model_cls.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That was not valid for the required JSON schema: {str(exc)[:500]}\n"
                                            "Reply again with ONLY valid JSON that matches the schema."},
            ]
        content = await self._post(messages)
        try:
            return model_cls.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise OllamaError(f"Model returned invalid JSON twice: {str(exc)[:200]}") from exc
