"""Provider factory: switching provider is a configuration change (LLM_PROVIDER)."""

from __future__ import annotations

from typing import Any

from ..provider import LLMProvider
from .template import TemplateProvider


def get_provider(settings: Any) -> LLMProvider:
    name = getattr(settings, "llm_provider", "template")
    key = getattr(settings, "llm_api_key", None) or ""
    model = getattr(settings, "llm_model", None)
    base_url = getattr(settings, "llm_base_url", None)
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(api_key=key, model=model, base_url=base_url)
    if name == "openai":
        from .openai import OpenAIProvider

        return OpenAIProvider(api_key=key, model=model, base_url=base_url)
    return TemplateProvider()
