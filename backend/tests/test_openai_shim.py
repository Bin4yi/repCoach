"""DEMO SHIM tests: the OpenAI stand-in honours the same contract as the Ollama client."""
import json

import httpx
import pytest

from app.llm.ollama_client import OllamaError
from app.llm.openai_client import OpenAIClient
from app.llm.schemas import ProgressSummary

GOOD = {"trend": "stable", "highlights": [], "concerns": [], "client_message": "Steady work."}


def transport(*contents):
    calls = {"n": 0, "bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        calls["bodies"].append(json.loads(request.content))
        c = contents[min(calls["n"], len(contents) - 1)]
        calls["n"] += 1
        if isinstance(c, int):
            return httpx.Response(c, text="err")
        return httpx.Response(200, json={"choices": [{"message": {"content": c}}]})

    return httpx.MockTransport(handler), calls


async def test_valid_json_and_auth_header():
    t, calls = transport(json.dumps(GOOD))
    c = OpenAIClient("sk-test", "gpt-test", transport=t)
    out = await c.chat_json("sys", "user", ProgressSummary)
    assert out.client_message == "Steady work."
    body = calls["bodies"][0]
    assert body["model"] == "gpt-test" and body["response_format"] == {"type": "json_object"}
    assert "JSON schema" in body["messages"][0]["content"]
    assert (await c.health())["ok"]


async def test_invalid_json_retries_then_raises():
    t, calls = transport("nope", json.dumps(GOOD))
    assert (await OpenAIClient("k", "m", transport=t).chat_json("s", "u", ProgressSummary)).trend == "stable"
    assert calls["n"] == 2
    t2, _ = transport("nope")
    with pytest.raises(OllamaError):
        await OpenAIClient("k", "m", transport=t2).chat_json("s", "u", ProgressSummary)


async def test_rate_limit_retried_and_missing_key_unhealthy():
    t, calls = transport(429, json.dumps(GOOD))
    await OpenAIClient("k", "m", transport=t).chat_json("s", "u", ProgressSummary)
    assert calls["n"] == 2
    assert not (await OpenAIClient("", "m").health())["ok"]
