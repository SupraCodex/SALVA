"""Questions about an analysis (FR-18, design document §34 "mode questions").

A question is never sent to a language model. Rules recognise what the user asks:

* "what if" questions on the delay, the air temperature, the packaging or the maturity are
  converted into parameters and run through the same simulation engine as the stored run
  (same options, seed, number of draws and risk profile); nothing is saved;
* questions on the risk, the recommendation, its reasons, its uncertainty or the assumptions
  are answered from the stored results;
* anything else is declined with a hint on what can be asked or where to change a value.

Every number in an answer therefore comes from the engines, as for explanations (ADR-1).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import replace

from salva_core.recommendation import Policy, recommend
from salva_core.simulation import draw, run_all
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Analysis, SimulationRun
from app.deps import Caller
from app.errors import ApiError, not_found
from app.repositories import lots as lots_repo
from app.schemas.analysis import QuestionIn, QuestionOut, SimulationCreate
from app.schemas.common import build
from app.services import engine
from app.services.analysis import core_lot
from app.services.explanation import REASONS, fmt_int, fmt_pct
from app.services.simulation import ACTION_LABELS, RISK_PROFILES, build_plan, params_for

_NUMBER = r"(\d+(?:[.,]\d+)?)"
_HOURS = re.compile(_NUMBER + r"\s*(?:h\b|hr|hrs|heure|heures|hour|hours)")
_DEGREES = re.compile(_NUMBER + r"\s*(?:°\s*c?|degres?|degrees?|deg\b|c\b)")
_PACKAGING = {
    "sack": r"\b(sac|sacs|sack|sacks|bag|bags)\b",
    "carton": r"\b(carton|cartons|cardboard|box|boxes)\b",
    "crate": r"\b(caisse|caisses|crate|crates)\b",
}
_MATURITY = {
    "green": r"\b(vert|verte|verts|green)\b",
    "breaker": r"\b(tournant|tournante|breaker|turning)\b",
    "ripe": r"\b(mur|mure|murs|mures|ripe)\b",
}
_INTENTS = [
    ("why", r"\b(pourquoi|why|explique|expliquer|explain|raison|reason)"),
    ("uncertainty", r"(confian|certain|incertitude|uncertain|confidence|fiab|reliab|\bsure\b|\bsur de\b)"),
    ("assumptions", r"(hypothes|assumption|source|donnee|\bdata\b)"),
    (
        "recommendation",
        r"(recommand|recommend|meilleur|\bbest\b|que faire|quoi faire|should|what to do|option)",
    ),
    ("risk", r"(risque|\brisk|perte|\bloss|\blose|abim|spoil|pourri|rot)"),
]
_EDITOR = r"(\bprix\b|\bprice|absorption|\bcout|\bcost|transport|stockage|storage)"

TEXT = {
    "fr": {
        "what_if": "Avec {changes}, la meilleure option serait « {best} » : environ {p50} nets "
        "(plage {p10} à {p90}), confiance {confidence}. Aujourd'hui : « {current} », {current_p50} nets.",
        "what_if_none": "Avec {changes}, aucune option ne se détache : les meilleures options sont trop proches "
        "compte tenu de l'incertitude.",
        "what_if_empty": "Avec {changes}, aucune option réalisable ne peut être simulée.",
        "not_saved": " Ce test n'est pas enregistré : modifiez le lot ou les hypothèses pour le conserver.",
        "risk": "Perte de valeur probable entre {p10} et {p90}, valeur centrale {p50} (risque {level}).",
        "recommendation": "Option recommandée : « {best} », environ {p50} nets (plage {p10} à {p90}), "
        "confiance {confidence}.",
        "recommendation_none": "Aucune option ne se détache clairement ; comparez les deux meilleures selon vos "
        "contraintes.",
        "why": "Motifs retenus par le moteur de recommandation : {reasons}.",
        "why_none": "Le moteur n'a pas relevé de motif particulier : l'option recommandée a simplement la "
        "meilleure valeur nette ajustée au risque.",
        "uncertainty": "L'option recommandée est la meilleure dans {prob} des {n} simulations (confiance "
        "{confidence}). La perte du lot est comprise entre {p10} et {p90} dans 80 % des cas simulés.",
        "assumptions": "Hypothèses principales : {items}. La liste complète est dans l'onglet Décisions et sur "
        "la page Hypothèses.",
        "editor": "Pour tester un autre prix, une autre absorption, un autre coût ou une autre durée de "
        "stockage, utilisez « Modifier les hypothèses » dans l'onglet Décisions.",
        "unsupported": "Je peux répondre sur le risque, l'option recommandée, ses raisons et son incertitude, "
        "ou tester « et si » le retard, la température, l'emballage ou la maturité changeait "
        "(par exemple : « et si le retard était de 24 h ? »).",
        "no_simulation": "Lancez d'abord la simulation des décisions pour poser cette question.",
        "delay_h": "un retard de {v} h",
        "temp_c": "une température de l'air de {v} °C",
        "packaging": "un emballage « {v} »",
        "maturity": "une maturité « {v} »",
        "and": " et ",
        "confidence": {"high": "élevée", "medium": "moyenne", "low": "faible", "none": "aucune"},
        "level": {"low": "faible", "medium": "moyen", "high": "élevé"},
        "packaging_names": {"crate": "caisse ajourée", "carton": "carton", "sack": "sac"},
        "maturity_names": {"green": "vert", "breaker": "tournant", "ripe": "mûr"},
    },
    "en": {
        "what_if": "With {changes}, the best option would be “{best}”: about {p50} net "
        "(range {p10} to {p90}), {confidence} confidence. Currently: “{current}”, {current_p50} net.",
        "what_if_none": "With {changes}, no option clearly stands out: the best options are too close given the "
        "uncertainty.",
        "what_if_empty": "With {changes}, no feasible option can be simulated.",
        "not_saved": " This test is not saved: change the lot or the assumptions to keep it.",
        "risk": "Likely loss of value between {p10} and {p90}, central value {p50} ({level} risk).",
        "recommendation": "Recommended option: “{best}”, about {p50} net (range {p10} to {p90}), "
        "{confidence} confidence.",
        "recommendation_none": "No option clearly stands out; compare the two best ones against your constraints.",
        "why": "Reasons found by the recommendation engine: {reasons}.",
        "why_none": "The engine found no particular reason: the recommended option simply has the best "
        "risk-adjusted net value.",
        "uncertainty": "The recommended option is the best in {prob} of the {n} simulations ({confidence} "
        "confidence). The lot's loss lies between {p10} and {p90} in 80% of simulated cases.",
        "assumptions": "Main assumptions: {items}. The full list is on the Decisions tab and the Assumptions page.",
        "editor": "To test another price, absorption, cost or storage duration, use “Change the assumptions” on "
        "the Decisions tab.",
        "unsupported": "I can answer about the risk, the recommended option, its reasons and its uncertainty, or "
        "test “what if” the delay, temperature, packaging or maturity changed (for example: “what if the "
        "delay were 24 h?”).",
        "no_simulation": "Simulate the decisions first to ask this question.",
        "delay_h": "a {v} h delay",
        "temp_c": "an air temperature of {v} °C",
        "packaging": "“{v}” packaging",
        "maturity": "“{v}” maturity",
        "and": " and ",
        "confidence": {"high": "high", "medium": "medium", "low": "low", "none": "no"},
        "level": {"low": "low", "medium": "medium", "high": "high"},
        "packaging_names": {"crate": "ventilated crate", "carton": "carton", "sack": "sack"},
        "maturity_names": {"green": "green", "breaker": "breaker", "ripe": "ripe"},
    },
}


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in plain if not unicodedata.combining(c)).replace("’", "'")


def _number(raw: str) -> float:
    return float(raw.replace(",", "."))


def parse_changes(question: str) -> dict[str, float | str]:
    """Parameters of a "what if" question, or an empty dict when it is not one."""
    q = normalize(question)
    changes: dict[str, float | str] = {}
    if re.search(r"(retard|delay|late|attente|wait)", q):
        m = _HOURS.search(q) or (re.search(_NUMBER, q) if not _DEGREES.search(q) else None)
        if m:
            changes["delay_h"] = _number(m.group(1))
    if re.search(r"(temperature|chaud|chaleur|froid|hot|heat|cold|°|degre|degree)", q):
        m = _DEGREES.search(q)
        if m:
            changes["temp_c"] = _number(m.group(1))
    if re.search(r"(emballage|packag|conditionn|\ben\b|\bin\b)", q):
        for code, pattern in _PACKAGING.items():
            if re.search(pattern, q):
                changes["packaging"] = code
                break
    if re.search(
        r"(maturite|maturity|stade|stage|recolte|harvest|\bmur|ripe|vert|green|tournant|breaker)", q
    ):
        for code, pattern in _MATURITY.items():
            if re.search(pattern, q):
                changes["maturity"] = code
                break
    return changes


def classify(question: str) -> str:
    q = normalize(question)
    for kind, pattern in _INTENTS:
        if re.search(pattern, q):
            return kind
    if re.search(_EDITOR, q):
        return "editor"
    return "unsupported"


def _latest_run(db: Session, analysis: Analysis) -> SimulationRun | None:
    return db.scalar(
        select(SimulationRun)
        .where(SimulationRun.analysis_id == analysis.id)
        .order_by(SimulationRun.created_at.desc())
        .limit(1)
    )


def _validate(changes: dict[str, float | str]) -> None:
    errors = []
    delay = changes.get("delay_h")
    if isinstance(delay, float) and not 0 <= delay <= 72:
        errors.append({"field": "question", "code": "out_of_range", "message": "delay must be 0-72 h"})
    temp = changes.get("temp_c")
    if isinstance(temp, float) and not 0 <= temp <= 50:
        errors.append({"field": "question", "code": "out_of_range", "message": "temperature must be 0-50 °C"})
    if errors:
        raise ApiError(422, "validation-error", "One or more fields are invalid.", errors)


def _describe(changes: dict[str, float | str], lang: str) -> str:
    t = TEXT[lang]
    parts = []
    for key in ("delay_h", "temp_c", "packaging", "maturity"):
        if key not in changes:
            continue
        value = changes[key]
        if key == "packaging":
            value = t["packaging_names"][str(value)]
        elif key == "maturity":
            value = t["maturity_names"][str(value)]
        elif isinstance(value, float):
            value = f"{value:g}".replace(".", ",") if lang == "fr" else f"{value:g}"
        parts.append(t[key].format(v=value))
    return t["and"].join(parts)


def _best_row(run: SimulationRun):
    reco = run.recommendation
    if reco is None or reco.best_scenario_id is None:
        return None
    return next((s for s in run.scenarios if s.id == reco.best_scenario_id), None)


def _what_if(db: Session, analysis: Analysis, run: SimulationRun, changes: dict, lang: str) -> QuestionOut:
    t = TEXT[lang]
    lot = analysis.lot
    request = SimulationCreate.model_validate(run.request)
    plan = build_plan(db, lot, analysis, request)
    clot = core_lot(lot, analysis)
    if "delay_h" in changes:
        planned = max(0.0, clot.remaining_h - clot.delay_h)
        clot = replace(
            clot, delay_h=float(changes["delay_h"]), remaining_h=planned + float(changes["delay_h"])
        )
    if "temp_c" in changes:
        clot = replace(clot, temp_c=float(changes["temp_c"]))
    if "packaging" in changes:
        clot = replace(clot, packaging=str(changes["packaging"]))
    if "maturity" in changes:
        clot = replace(clot, maturity=str(changes["maturity"]))
    p = params_for(lot, request)
    model = engine.loss_model(lot.product_code)
    shocks = draw(run.n_draws, run.seed, market_ids=sorted({o.market.id for o in plan.options}))
    try:
        results = run_all(model, clot, plan.options, shocks, p)
        reco = recommend(results, Policy(lam=RISK_PROFILES[run.risk_profile]))
    except ValueError as exc:
        raise ApiError(422, "question-invalid", f"The question could not be simulated: {exc}") from exc

    by_id = {r.id: r for r in results}
    best = by_id.get(reco.best_id) if reco.best_id else None
    label = None
    if best is not None:
        meta = plan.meta.get(best.id)
        if meta is not None:
            label = meta.label()
        else:
            label = dict(zip(("fr", "en"), ACTION_LABELS["optimized_split"], strict=True))
    current = _best_row(run)
    current_label = current.label if current is not None else None
    current_p50 = (current.results.get("net_value_fcfa") or {}).get("p50") if current is not None else None
    described = _describe(changes, lang)
    if best is None:
        answer = t["what_if_empty"].format(changes=described)
    elif reco.no_clear_winner:
        answer = t["what_if_none"].format(changes=described)
    else:
        answer = t["what_if"].format(
            changes=described,
            best=label[lang] if label else "-",
            p50=f"{fmt_int(best.net_p50, lang)} FCFA",
            p10=f"{fmt_int(best.net_p10, lang)} FCFA",
            p90=f"{fmt_int(best.net_p90, lang)} FCFA",
            confidence=t["confidence"].get(reco.confidence, reco.confidence),
            current=current_label[lang] if current_label else "-",
            current_p50=f"{fmt_int(current_p50, lang)} FCFA",
        )
    answer += t["not_saved"]
    return build(
        QuestionOut,
        kind="what_if",
        answer=answer,
        what_if={
            "changes": changes,
            "best_label": label,
            "best_action": best.action if best else None,
            "confidence": reco.confidence,
            "no_clear_winner": reco.no_clear_winner,
            "net_value_fcfa": {
                "p10": best.net_p10 if best else None,
                "p50": best.net_p50 if best else None,
                "p90": best.net_p90 if best else None,
            },
            "loss_fraction": {
                "p10": best.loss_p10 if best else None,
                "p50": best.loss_p50 if best else None,
                "p90": best.loss_p90 if best else None,
            },
            "current_best_label": current_label,
            "current_net_p50_fcfa": current_p50,
        },
    )


def ask(db: Session, caller: Caller, analysis_id: uuid.UUID, body: QuestionIn) -> QuestionOut:
    analysis = lots_repo.analysis(db, caller.organization_id, analysis_id)
    if analysis is None:
        raise not_found("Analysis")
    lang = body.lang
    t = TEXT[lang]
    run = None
    if body.simulation_id is not None:
        run = lots_repo.simulation(db, caller.organization_id, body.simulation_id)
        if run is None or run.analysis_id != analysis.id:
            raise not_found("Simulation")
    else:
        run = _latest_run(db, analysis)

    changes = parse_changes(body.question)
    if changes:
        _validate(changes)
        if run is None:
            return build(QuestionOut, kind="unsupported", answer=t["no_simulation"])
        return _what_if(db, analysis, run, changes, lang)

    kind = classify(body.question)
    if kind == "risk":
        answer = t["risk"].format(
            p10=fmt_pct(analysis.loss_p10, lang),
            p50=fmt_pct(analysis.loss_p50, lang),
            p90=fmt_pct(analysis.loss_p90, lang),
            level=t["level"].get(analysis.risk_level, analysis.risk_level),
        )
        return build(QuestionOut, kind="risk", answer=answer)
    if kind == "editor":
        return build(QuestionOut, kind="unsupported", answer=t["editor"])
    if kind == "unsupported":
        return build(QuestionOut, kind="unsupported", answer=t["unsupported"])
    if run is None or run.recommendation is None:
        return build(QuestionOut, kind="unsupported", answer=t["no_simulation"])

    reco = run.recommendation
    best = _best_row(run)
    if kind == "recommendation":
        if reco.no_clear_winner or best is None:
            return build(QuestionOut, kind="recommendation", answer=t["recommendation_none"])
        net = best.results.get("net_value_fcfa") or {}
        answer = t["recommendation"].format(
            best=best.label[lang],
            p50=f"{fmt_int(net.get('p50'), lang)} FCFA",
            p10=f"{fmt_int(net.get('p10'), lang)} FCFA",
            p90=f"{fmt_int(net.get('p90'), lang)} FCFA",
            confidence=t["confidence"].get(reco.confidence, reco.confidence),
        )
        return build(QuestionOut, kind="recommendation", answer=answer)
    if kind == "why":
        reasons = [REASONS[lang][c] for c in reco.rationale_codes if c in REASONS[lang]]
        answer = t["why"].format(reasons=", ".join(reasons)) if reasons else t["why_none"]
        return build(QuestionOut, kind="why", answer=answer)
    if kind == "uncertainty":
        answer = t["uncertainty"].format(
            prob=fmt_pct(reco.prob_best, lang),
            n=fmt_int(run.n_draws, lang),
            confidence=t["confidence"].get(reco.confidence, reco.confidence),
            p10=fmt_pct(analysis.loss_p10, lang),
            p90=fmt_pct(analysis.loss_p90, lang),
        )
        return build(QuestionOut, kind="uncertainty", answer=answer)
    items = [a for a in run.assumptions if not a.get("user_override")][:4]
    names = ", ".join(_assumption_text(a, lang) for a in items)
    return build(QuestionOut, kind="assumptions", answer=t["assumptions"].format(items=names))


_ASSUMPTION_NAMES = {
    "fr": {
        "temperature_air_c": "température de l'air",
        "remaining_transit_h": "trajet restant",
        "hold_h": "durée de stockage simulée",
        "transport_fcfa_kg_km": "coût de transport",
        "surplus_price_fraction": "prix du surplus",
        "position": "position du camion inconnue",
    },
    "en": {
        "temperature_air_c": "air temperature",
        "remaining_transit_h": "remaining travel",
        "hold_h": "simulated storage duration",
        "transport_fcfa_kg_km": "transport cost",
        "surplus_price_fraction": "surplus price",
        "position": "truck position unknown",
    },
}


def _assumption_text(item: dict, lang: str) -> str:
    key = str(item.get("key", ""))
    name = _ASSUMPTION_NAMES[lang].get(key, key.split(":")[0])
    value = item.get("value")
    if key == "position" or not isinstance(value, int | float):
        return name
    number = f"{value:g}".replace(".", ",") if lang == "fr" else f"{value:g}"
    unit = item.get("unit") or ""
    return f"{name} {number} {unit}".strip()
