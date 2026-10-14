"""Explanation of a recommendation (FR-11, FR-12): template first, validated LLM when configured.

The facts sent to the LLM are built here from stored, computed values only. Lot notes and
any other free text typed by users are never included (SEC-03, CA-14).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Explanation, Recommendation, SimulationRun
from app.deps import Caller
from app.errors import not_found
from app.llm.explain import explain as run_explain
from app.llm.providers import get_provider
from app.llm.schemas import ExplanationFacts, Lang, ScenarioFact
from app.repositories import lots as lots_repo
from app.schemas.outcome import ExplanationOut
from app.services import audit, engine

RISK = {
    "fr": {"low": "faible", "medium": "moyen", "high": "élevé"},
    "en": {"low": "low", "medium": "medium", "high": "high"},
}
CONFIDENCE = {
    "fr": {"high": "haute", "medium": "moyenne", "low": "faible", "none": "aucune"},
    "en": {"high": "high", "medium": "medium", "low": "low", "none": "none"},
}
FACTORS = {
    "fr": {
        "temperature": "la température",
        "age": "l'âge du lot",
        "transit": "la durée du trajet",
        "delay": "le retard",
        "maturity": "la maturité",
        "packaging": "l'emballage",
        "storage": "le stockage",
        "chilling": "le froid excessif",
    },
    "en": {
        "temperature": "temperature",
        "age": "lot age",
        "transit": "transit time",
        "delay": "delay",
        "maturity": "maturity",
        "packaging": "packaging",
        "storage": "storage",
        "chilling": "chilling",
    },
}
REASONS = {
    "fr": {
        "HIGH_TEMP": "température élevée",
        "DELAY": "retard de transport",
        "MARKET_SATURATION_AT_DEST": "saturation du marché de destination",
        "STORAGE_CAPACITY_BINDING": "capacité de stockage limitante",
        "LONG_DETOUR_COST": "coût du détour",
        "LOW_RISK_NO_URGENT_ACTION": "risque faible, pas d'urgence",
        "SINGLE_FEASIBLE_ACTION": "une seule option réalisable",
        "ALL_OPTIONS_NEGATIVE": "toutes les options ont une valeur nette négative",
        "NO_CLEAR_WINNER": "écart trop faible entre les meilleures options",
        "NO_FEASIBLE_ACTION": "aucune option réalisable",
        "ALL_OPTIONS_DISCOURAGED": "toutes les options dépassent la durée de vie estimée",
        "HEAVY_LOSSES_LIKELY": "pertes importantes probables",
    },
    "en": {
        "HIGH_TEMP": "high temperature",
        "DELAY": "transport delay",
        "MARKET_SATURATION_AT_DEST": "destination market saturation",
        "STORAGE_CAPACITY_BINDING": "storage capacity is limiting",
        "LONG_DETOUR_COST": "detour cost",
        "LOW_RISK_NO_URGENT_ACTION": "low risk, no urgent action",
        "SINGLE_FEASIBLE_ACTION": "only one feasible option",
        "ALL_OPTIONS_NEGATIVE": "every option has a negative net value",
        "NO_CLEAR_WINNER": "the best options are too close",
        "NO_FEASIBLE_ACTION": "no feasible option",
        "ALL_OPTIONS_DISCOURAGED": "every option exceeds the estimated shelf life",
        "HEAVY_LOSSES_LIKELY": "heavy losses are likely",
    },
}
ASSUMPTIONS = {
    "fr": {
        "model": "Paramètres du modèle cinétique non validés sur le terrain.",
        "absorption": "La capacité d'absorption des marchés est une hypothèse.",
        "position": "La position actuelle du camion est inconnue : les détours sont calculés depuis le départ.",
        "temp_auto": "Température issue de la météo automatique (air, pas produit).",
        "temp_manual": "Température saisie manuellement.",
        "temp_default": "Température par défaut (météo indisponible) : hypothèse.",
        "overrides": "Certaines hypothèses ont été modifiées par l'utilisateur.",
    },
    "en": {
        "model": "Kinetic model parameters are not validated on field data.",
        "absorption": "Market absorption capacity is an assumption.",
        "position": "The truck's live position is unknown: detours are computed from the departure place.",
        "temp_auto": "Temperature from automatic weather data (air, not produce).",
        "temp_manual": "Temperature entered manually.",
        "temp_default": "Default temperature (weather unavailable): assumption.",
        "overrides": "Some assumptions were changed by the user.",
    },
}
NNBSP = " "


def fmt_int(value: float | None, lang: Lang) -> str:
    if value is None:
        return "-"
    text = f"{round(value):,}"
    return text.replace(",", NNBSP) if lang == "fr" else text


def fmt_pct(fraction: float | None, lang: Lang) -> str:
    if fraction is None:
        return "-"
    pct = round(100 * fraction)
    return f"{pct}{NNBSP}%" if lang == "fr" else f"{pct}%"


def build_facts(run: SimulationRun, lang: Lang) -> ExplanationFacts:
    analysis, reco = run.analysis, run.recommendation
    lot = analysis.lot
    by_key = {s.key: s for s in run.scenarios}
    ranked = [by_key[k] for k in reco.ranked_keys if k in by_key]
    eligible = ([s for s in ranked if s.feasible and not s.discouraged] or [s for s in ranked if s.feasible])[
        :5
    ]  # least-bad comparison (§33)
    scenarios = []
    for s in eligible:
        r = s.results
        scenarios.append(
            ScenarioFact(
                label=s.label[lang],
                recoverable_kg_p50=f"{fmt_int(r['recoverable_kg']['p50'], lang)} kg",
                net_p10=f"{fmt_int(r['net_value_fcfa']['p10'], lang)} FCFA",
                net_p50=f"{fmt_int(r['net_value_fcfa']['p50'], lang)} FCFA",
                net_p90=f"{fmt_int(r['net_value_fcfa']['p90'], lang)} FCFA",
                prob_best=fmt_pct(s.prob_best, lang),
            )
        )
    best = next((s for s in run.scenarios if s.id == reco.best_scenario_id), None)
    factors = [
        FACTORS[lang].get(f["name"], f["name"])
        for f in analysis.top_factors
        if f["direction"] == "increases_risk"
    ][:3]
    temp_source = analysis.feature_sources.get("temp_air_c", "")
    temp_key = (
        "temp_manual"
        if temp_source == "manual"
        else "temp_auto"
        if temp_source == "open-meteo"
        else "temp_default"
    )
    assumptions = [ASSUMPTIONS[lang][k] for k in ("model", "absorption", "position", temp_key)]
    if any(a.get("user_override") for a in run.assumptions):
        assumptions.append(ASSUMPTIONS[lang]["overrides"])
    return ExplanationFacts(
        product=engine.product_label(lot.product_code, lang).lower(),
        quantity=f"{fmt_int(lot.quantity_kg, lang)} kg",
        risk_level=RISK[lang][analysis.risk_level],
        loss_p10=fmt_pct(analysis.loss_p10, lang),
        loss_p50=fmt_pct(analysis.loss_p50, lang),
        loss_p90=fmt_pct(analysis.loss_p90, lang),
        top_factors=factors,
        scenarios=scenarios,
        best_action=best.label[lang] if best and not reco.no_clear_winner else None,
        confidence=CONFIDENCE[lang][reco.confidence],
        best_probability=fmt_pct(reco.prob_best, lang),
        candidates=[s.label[lang] for s in ranked[:2]] if reco.no_clear_winner else [],
        reasons=[REASONS[lang][c] for c in reco.rationale_codes if c in REASONS[lang]],
        reason_codes=list(reco.rationale_codes),
        assumptions=assumptions,
        low_risk=analysis.risk_level == "low",
    )


def _recommendation_or_404(db: Session, caller: Caller, reco_id: uuid.UUID) -> Recommendation:
    reco = lots_repo.recommendation(db, caller.organization_id, reco_id)
    if reco is None:
        raise not_found("Recommendation")
    return reco


async def explain(db: Session, caller: Caller, reco_id: uuid.UUID, lang: Lang) -> Explanation:
    reco = _recommendation_or_404(db, caller, reco_id)
    settings = get_settings()
    cached = db.scalar(
        select(Explanation)
        .where(Explanation.recommendation_id == reco.id, Explanation.lang == lang)
        .order_by(Explanation.created_at.desc())
        .limit(1)
    )
    # Results are immutable: a validated LLM text, or a template when no LLM is configured,
    # never needs regenerating. A template produced after an LLM failure is retried.
    if cached is not None and (cached.source == "llm" or settings.llm_provider == "template"):
        return cached
    run = reco.simulation_run
    facts = build_facts(run, lang)
    try:
        provider = get_provider(settings)
    except Exception as exc:  # noqa: BLE001 - misconfiguration (missing key): use the template
        from app.llm.providers.template import TemplateProvider

        provider = TemplateProvider()
        provider_error = f"provider_unavailable:{type(exc).__name__}"
    else:
        provider_error = None
    result = await run_explain(facts, lang, provider, timeout=settings.llm_timeout_s)
    reason = result.rejection_reason or provider_error
    row = Explanation(
        recommendation_id=reco.id,
        lang=lang,
        source=result.source,
        provider=result.provider
        if result.source == "llm"
        else (settings.llm_provider if reason else "template"),
        validated=result.validated,
        rejection_reason=reason,
        content={
            "summary": result.summary,
            "risk_explanation": result.risk_explanation,
            "scenario_comparison": result.scenario_comparison,
            "recommendation_text": result.recommendation_text,
            "caveats": result.caveats,
        },
    )
    db.add(row)
    if reason:
        audit.record(
            db,
            "llm_rejected",
            "recommendation",
            reco.id,
            organization_id=caller.organization_id,
            user_id=caller.user_id,
            detail={"reason": reason[:120], "provider": settings.llm_provider},
        )
    db.commit()
    db.refresh(row)
    return row


def to_out(e: Explanation) -> ExplanationOut:
    c = e.content
    return ExplanationOut(
        id=e.id,
        recommendation_id=e.recommendation_id,
        lang=e.lang,
        source=e.source,
        provider=e.provider,
        validated=e.validated,
        summary=c["summary"],
        risk_explanation=c["risk_explanation"],
        scenario_comparison=c["scenario_comparison"],
        recommendation_text=c["recommendation_text"],
        caveats=c["caveats"],
        created_at=e.created_at,
    )
