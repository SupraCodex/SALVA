"""POST /analyses/{id}/explanation — API side only.

Text generation (facts, template, LLM provider, number validator) belongs to R5 in `app/llm/`.
Contract expected from R5:

    # app/llm/service.py
    async def generate(analysis: dict, lang: str) -> dict:
        '''analysis = the AnalysisOut JSON (lot notes are never included).
        Must ALWAYS return (template fallback on any LLM failure):
        {"source": "template"|"llm", "provider": str|None, "validated": bool,
         "summary": str, "risk": str, "scenarios": str, "caveats": [str, ...]}'''

The API stores the result (immutable cache per analysis + language) and returns it.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Explanation
from app.deps import Caller
from app.errors import ApiError
from app.repositories import analyses as analyses_repo
from app.schemas.analysis import ExplanationOut
from app.services import analysis_service

log = logging.getLogger("salva.explanation")
REQUIRED = ("summary", "risk", "scenarios")


def _generator():
    try:
        from app.llm.service import generate
    except ImportError:
        raise ApiError(503, "explanation-unavailable",
                       "Explanation layer not installed yet (app/llm/service.py).") from None
    return generate


async def explain(db: Session, caller: Caller, analysis_id: int, lang: str) -> Explanation:
    a = analysis_service.get_or_404(db, caller, analysis_id)
    cached = analyses_repo.cached_explanation(db, a.id, lang)
    if cached is not None and cached.source == "llm":
        return cached  # analysis is immutable: an LLM explanation never needs regenerating
    generate = _generator()
    payload = analysis_service.to_out(a).model_dump(mode="json")
    try:
        out = await asyncio.wait_for(generate(payload, lang), timeout=get_settings().llm_timeout_s)
    except Exception as e:
        log.warning("explanation_failed: %s", type(e).__name__)
        if cached is not None:
            return cached
        raise ApiError(503, "explanation-unavailable", "The explanation could not be generated.") from e
    if not isinstance(out, dict) or any(not isinstance(out.get(k), str) for k in REQUIRED):
        raise ApiError(503, "explanation-invalid", "The explanation layer returned an invalid payload.")
    source = out.get("source") if out.get("source") in ("template", "llm") else "template"
    content = {k: out[k] for k in REQUIRED}
    content["caveats"] = [str(c) for c in out.get("caveats", [])]
    e = Explanation(analysis_id=a.id, lang=lang, source=source, provider=out.get("provider"),
                    validated=bool(out.get("validated", source == "template")), content=content)
    return analyses_repo.save_explanation(db, e)


def to_out(e: Explanation) -> ExplanationOut:
    c = e.content
    return ExplanationOut(id=e.id, analysis_id=e.analysis_id, lang=e.lang, source=e.source, provider=e.provider,
                          validated=e.validated, summary=c["summary"], risk=c["risk"], scenarios=c["scenarios"],
                          caveats=c.get("caveats", []))
