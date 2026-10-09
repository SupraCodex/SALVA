"""Provider factory: switching provider = changing LLM_PROVIDER."""
from __future__ import annotations

from typing import Any

from ..provider import LLMProvider
from .template import TemplateProvider


def get_provider(settings: Any) -> LLMProvider:
    name = getattr(settings, "llm_provider", "template")
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(
            api_key=getattr(settings, "llm_api_key", None) or "",
            model=getattr(settings, "llm_model", "gemini-2.5-flash"),
        )
    return TemplateProvider()
