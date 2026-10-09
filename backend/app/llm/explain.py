"""Single entry point for the explanation service.

    result = await explain(facts, "fr", get_provider(settings))

Never raises: any failure, timeout or invented number => template (HTTP 200).
"""
from __future__ import annotations

import logging

from .prompts import SYSTEM_PROMPT, build_user_prompt
from .provider import LLMProvider
from .providers.template import render
from .schemas import (
    GEMINI_SCHEMA,
    ExplanationFacts,
    ExplanationOut,
    ExplanationResult,
    Lang,
)
from .validator import invented_numbers

log = logging.getLogger("salva.llm")


def _template(facts: ExplanationFacts, lang: Lang) -> ExplanationResult:
    return ExplanationResult(**render(facts, lang).model_dump(),
                             source="template", lang=lang)


async def explain(
    facts: ExplanationFacts,
    lang: Lang,
    provider: LLMProvider,
    timeout: float = 8.0,
) -> ExplanationResult:
    if provider.name == "template":
        return _template(facts, lang)

    facts_text = facts.model_dump_json()
    try:
        raw = await provider.generate_json(
            SYSTEM_PROMPT,
            build_user_prompt(facts, lang),
            GEMINI_SCHEMA,
            timeout=timeout,
        )
        out = ExplanationOut.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - fallback must catch everything
        log.warning("llm failed, using template: %s", type(exc).__name__)
        return _template(facts, lang)

    text = f"{out.summary} {out.risk} {out.scenarios} {out.caveats}"
    bad = invented_numbers(text, facts_text)
    if bad:
        log.warning("llm invented numbers %s, using template", sorted(bad))
        return _template(facts, lang)

    return ExplanationResult(**out.model_dump(), source="llm", lang=lang)
