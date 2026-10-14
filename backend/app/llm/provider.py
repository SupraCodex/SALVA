"""Common interface for every LLM provider (template, gemini, ...)."""

from __future__ import annotations

from typing import Protocol


class LLMError(Exception):
    """Any provider failure (network, timeout, bad JSON, bad status)."""


class LLMProvider(Protocol):
    name: str

    async def generate_json(self, system: str, user: str, schema: dict, timeout: float = 8.0) -> dict: ...
