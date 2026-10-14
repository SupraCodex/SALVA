"""Single entry point of the explanation layer (design document §23.4).

    result = await explain(facts, "fr", provider)

The deterministic template is computed first, so it is always available. The LLM output is
validated (schema, numbers, decision, wording, language); any failure, timeout or rejection
returns the template with the rejection reason. This function never raises.
"""

from __future__ import annotations

import asyncio
import logging

from .prompts import SYSTEM_PROMPT, build_user_prompt
from .provider import LLMProvider
from .providers.template import render
from .schemas import (
    JSON_SCHEMA,
    ExplanationFacts,
    ExplanationOut,
    ExplanationResult,
    Lang,
)
from .validator import check

log = logging.getLogger("salva.llm")


def _template(facts: ExplanationFacts, lang: Lang, reason: str | None = None) -> ExplanationResult:
    return ExplanationResult(
        **render(facts, lang).model_dump(),
        source="template",
        provider="template",
        validated=True,
        lang=lang,
        rejection_reason=reason,
    )


async def explain(
    facts: ExplanationFacts, lang: Lang, provider: LLMProvider, timeout: float = 8.0
) -> ExplanationResult:
    template = _template(facts, lang)
    if provider.name == "template":
        return template
    try:
        raw = await asyncio.wait_for(
            provider.generate_json(
                SYSTEM_PROMPT,
                build_user_prompt(facts, lang),
                JSON_SCHEMA,
                timeout=timeout,
            ),
            timeout=timeout,
        )
        out = ExplanationOut.model_validate(raw)
    except TimeoutError:
        log.warning("llm_rejected", extra={"reason": "timeout", "provider": provider.name})
        return _template(facts, lang, "timeout")
    except Exception as exc:  # noqa: BLE001 - the fallback must catch everything
        reason = f"error:{type(exc).__name__}"
        log.warning("llm_rejected", extra={"reason": reason, "provider": provider.name})
        return _template(facts, lang, reason)
    reason = check(out, facts, lang)
    if reason:
        log.warning("llm_rejected", extra={"reason": reason, "provider": provider.name})
        return _template(facts, lang, reason)
    return ExplanationResult(
        **out.model_dump(),
        source="llm",
        provider=provider.name,
        validated=True,
        lang=lang,
    )
