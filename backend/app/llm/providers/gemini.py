"""Gemini through its REST API (models.generateContent). The API key is never logged.

Docs: https://ai.google.dev/api/generate-content and https://ai.google.dev/gemini-api/docs/models
"""

from __future__ import annotations

import json

import httpx

from ..provider import LLMError
from ..schemas import GEMINI_SCHEMA

DEFAULT_MODEL = "gemini-3.5-flash-lite"
_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str | None = None, base_url: str | None = None) -> None:
        if not api_key:
            raise LLMError("missing LLM_API_KEY")
        self._api_key = api_key
        self._model = model or DEFAULT_MODEL
        self._url = (base_url.rstrip("/") + "/models/{model}:generateContent") if base_url else _URL

    async def generate_json(self, system: str, user: str, schema: dict, timeout: float = 8.0) -> dict:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 900,
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_SCHEMA,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    self._url.format(model=self._model),
                    headers={"x-goog-api-key": self._api_key},
                    json=body,
                )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            # Only the exception type: the message could contain the URL or the key.
            raise LLMError(f"gemini call failed: {type(exc).__name__}") from exc
        if not isinstance(data, dict):
            raise LLMError("gemini returned non-object JSON")
        return data
