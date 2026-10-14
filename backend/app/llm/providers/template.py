"""Deterministic explanation (FR-11). Always available: no network, no key, no invented number."""

from __future__ import annotations

import json

from ..schemas import ExplanationFacts, ExplanationOut, Lang

_T = {
    "fr": {
        "summary_best": "Dans la simulation actuelle, l'option « {best} » présente le meilleur potentiel "
        "de récupération ({net} nets estimés en valeur médiane).",
        "summary_none": "Dans la simulation actuelle, aucune option ne se détache clairement : "
        "« {a} » et « {b} » donnent des résultats trop proches compte tenu de l'incertitude.",
        "summary_single": "Dans la simulation actuelle, une seule option est réalisable : « {best} ».",
        "summary_empty": "Aucune option réalisable n'a pu être simulée pour ce lot.",
        "risk": "Le risque de perte de valeur de ce lot de {quantity} de {product} est {level} : "
        "perte probable entre {p10} et {p90}, valeur centrale {p50}.",
        "factors": " L'estimation est surtout influencée par : {factors}.",
        "low": " Aucune action urgente n'est nécessaire ; la simulation reste disponible pour comparer.",
        "scenario": "« {label} » : environ {kg} équivalents plein tarif, {p50} nets (plage {p10} à {p90}), "
        "meilleure option dans {prob} des simulations.",
        "no_scenario": "Aucun scénario réalisable.",
        "reco_best": "Recommandation : {best} (confiance {confidence} ; meilleure option dans {prob} "
        "des simulations).",
        "reco_none": "Pas de gagnant net : comparez « {a} » et « {b} » selon vos contraintes avant de décider.",
        "reco_empty": "Aucune recommandation ne peut être formulée sans option réalisable.",
        "reasons": " Motifs : {reasons}.",
        "base": "Estimation basée sur un modèle, non validée sur données terrain ; ce n'est pas une garantie.",
    },
    "en": {
        "summary_best": "In the current simulation, the option “{best}” has the best recovery "
        "potential ({net} net, median estimate).",
        "summary_none": "In the current simulation, no option clearly stands out: “{a}” and "
        "“{b}” are too close given the uncertainty.",
        "summary_single": "In the current simulation, only one option is feasible: “{best}”.",
        "summary_empty": "No feasible option could be simulated for this lot.",
        "risk": "The value-loss risk of this {quantity} {product} lot is {level}: likely loss between "
        "{p10} and {p90}, central value {p50}.",
        "factors": " The estimate is mostly driven by: {factors}.",
        "low": " No urgent action is needed; the simulation remains available for comparison.",
        "scenario": "“{label}”: about {kg} full-price equivalent, {p50} net (range {p10} to {p90}), "
        "best option in {prob} of simulations.",
        "no_scenario": "No feasible scenario.",
        "reco_best": "Recommendation: {best} (confidence {confidence}; best option in {prob} of simulations).",
        "reco_none": "No clear winner: compare “{a}” and “{b}” against your constraints before deciding.",
        "reco_empty": "No recommendation can be made without a feasible option.",
        "reasons": " Reasons: {reasons}.",
        "base": "Model-based estimate, not validated on field data; this is not a guarantee.",
    },
}


def render(facts: ExplanationFacts, lang: Lang) -> ExplanationOut:
    t = _T[lang]
    by_label = {s.label: s for s in facts.scenarios}
    if facts.best_action and facts.best_action in by_label:
        best = by_label[facts.best_action]
        if len(facts.scenarios) == 1:
            summary = t["summary_single"].format(best=best.label)
        else:
            summary = t["summary_best"].format(best=best.label, net=best.net_p50)
        reco = t["reco_best"].format(best=best.label, confidence=facts.confidence or "-", prob=best.prob_best)
    elif len(facts.candidates) >= 2:
        a, b = facts.candidates[:2]
        summary = t["summary_none"].format(a=a, b=b)
        reco = t["reco_none"].format(a=a, b=b)
    else:
        summary = t["summary_empty"]
        reco = t["reco_empty"]
    if facts.reasons:
        reco += t["reasons"].format(reasons=", ".join(facts.reasons))

    risk = t["risk"].format(
        quantity=facts.quantity,
        product=facts.product,
        level=facts.risk_level,
        p10=facts.loss_p10,
        p50=facts.loss_p50,
        p90=facts.loss_p90,
    )
    if facts.top_factors:
        risk += t["factors"].format(factors=", ".join(facts.top_factors))
    if facts.low_risk:
        risk += t["low"]

    lines = [
        t["scenario"].format(
            label=s.label,
            kg=s.recoverable_kg_p50,
            p50=s.net_p50,
            p10=s.net_p10,
            p90=s.net_p90,
            prob=s.prob_best,
        )
        for s in facts.scenarios
    ]
    comparison = " ".join(lines) if lines else t["no_scenario"]
    caveats = [t["base"], *facts.assumptions]
    return ExplanationOut(
        summary=summary[:400],
        risk_explanation=risk[:900],
        scenario_comparison=comparison[:1200],
        recommendation_text=reco[:900],
        caveats=caveats[:8],
    )


class TemplateProvider:
    name = "template"

    async def generate_json(self, system: str, user: str, schema: dict, timeout: float = 8.0) -> dict:
        payload = json.loads(user)
        facts = ExplanationFacts.model_validate(payload["facts"])
        return render(facts, payload["lang"]).model_dump()
