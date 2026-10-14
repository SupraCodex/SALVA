"""OpenAI-compatible Chat Completions provider (JSON mode). The API key is never logged.

Works with any service exposing ``POST {base_url}/chat/completions`` with
``response_format={"type": "json_object"}``. ``LLM_MODEL`` must be set explicitly.
Docs: https://platform.openai.com/docs/api-reference/chat
"""

from __future__ import annotations

import json

import httpx

from ..provider import LLMError

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str | None, base_url: str | None = None) -> None:
        if not api_key:
            raise LLMError("missing LLM_API_KEY")
        if not model:
            raise LLMError("missing LLM_MODEL")
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")

    async def generate_json(self, system: str, user: str, schema: dict, timeout: float = 8.0) -> dict:
        body = {
            "model": self._model,
            "temperature": 0.2,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": system + "\nJSON schema: " + json.dumps(schema),
                },
                {"role": "user", "content": user},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
            resp.raise_for_status()
            data = json.loads(resp.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"openai call failed: {type(exc).__name__}") from exc
        if not isinstance(data, dict):
            raise LLMError("openai returned non-object JSON")
        return data
