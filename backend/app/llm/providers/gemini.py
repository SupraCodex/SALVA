"""Gemini via REST (httpx). No SDK needed. The API key is never logged."""
from __future__ import annotations

import json

import httpx

from ..provider import LLMError

_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash") -> None:
        if not api_key:
            raise LLMError("missing LLM_API_KEY")
        self._api_key = api_key
        self._model = model

    async def generate_json(
        self, system: str, user: str, schema: dict, timeout: float = 8.0
    ) -> dict:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    _URL.format(model=self._model),
                    headers={"x-goog-api-key": self._api_key},
                    json=body,
                )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            # Only the exception type: the message could contain the URL/key.
            raise LLMError(f"gemini call failed: {type(exc).__name__}") from exc
        if not isinstance(data, dict):
            raise LLMError("gemini returned non-object JSON")
        return data
