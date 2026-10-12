"""Deterministic fallback. Always works: no network, no API key."""
from __future__ import annotations

import json

from ..schemas import ExplanationFacts, ExplanationOut, Lang

_RISK = {
    "fr": {"low": "faible", "medium": "moyen", "high": "élevé"},
    "en": {"low": "low", "medium": "medium", "high": "high"},
}


def render(facts: ExplanationFacts, lang: Lang) -> ExplanationOut:
    fr = lang == "fr"
    level = _RISK[lang].get(facts.risk_level, facts.risk_level)

    if facts.best_action:
        conf = f" ({facts.confidence})" if facts.confidence else ""
        summary = (
            f"L'option la mieux placée est : {facts.best_action}{conf}."
            if fr
            else f"The best-placed option is: {facts.best_action}{conf}."
        )
    else:
        summary = (
            "Aucune option ne se détache clairement : les écarts sont "
            "trop faibles face à l'incertitude."
            if fr
            else "No option clearly stands out: the gaps are too small "
            "compared with the uncertainty."
        )

    risk = (
        f"Risque de perte {level} pour ce lot de {facts.product} : "
        f"perte estimée entre {facts.loss_p10} et {facts.loss_p90}, "
        f"valeur centrale {facts.loss_p50}."
        if fr
        else f"{level.capitalize()} loss risk for this {facts.product} lot: "
        f"estimated loss between {facts.loss_p10} and {facts.loss_p90}, "
        f"central value {facts.loss_p50}."
    )

    lines = []
    for s in facts.scenarios:
        best = ""
        if s.prob_best:
            best = (
                f", meilleure option dans {s.prob_best} des cas"
                if fr
                else f", best option in {s.prob_best} of cases"
            )
        lines.append(
            f"{s.label} : {s.net_p10} à {s.net_p90} (médiane {s.net_p50}){best}."
            if fr
            else f"{s.label}: {s.net_p10} to {s.net_p90} "
            f"(median {s.net_p50}){best}."
        )
    scenarios = " ".join(lines) or (
        "Aucun scénario disponible." if fr else "No scenario available."
    )

    base = (
        "Estimation du modèle, non validée sur données terrain ; "
        "ce n'est pas une garantie."
        if fr
        else "Model estimate, not validated on field data; not a guarantee."
    )
    caveats = " ".join([base, *facts.assumptions])

    return ExplanationOut(
        summary=summary, risk=risk, scenarios=scenarios, caveats=caveats
    )


class TemplateProvider:
    name = "template"

    async def generate_json(
        self, system: str, user: str, schema: dict, timeout: float = 8.0
    ) -> dict:
        payload = json.loads(user)
        facts = ExplanationFacts.model_validate(payload["facts"])
        return render(facts, payload["lang"]).model_dump()
