import asyncio

import pytest

from app.llm.explain import explain
from app.llm.provider import LLMError
from app.llm.providers import get_provider
from app.llm.providers.template import TemplateProvider
from app.llm.schemas import ExplanationFacts, ScenarioFact

FACTS = ExplanationFacts(
    product="tomate",
    quantity="500 kg",
    risk_level="élevé",
    loss_p10="12 %",
    loss_p50="31 %",
    loss_p90="48 %",
    top_factors=["la température", "le retard"],
    best_action="Réorienter vers Mokolo (Yaoundé)",
    confidence="moyenne",
    best_probability="62 %",
    scenarios=[
        ScenarioFact(
            label="Réorienter vers Mokolo (Yaoundé)",
            recoverable_kg_p50="310 kg",
            net_p10="120 000 FCFA",
            net_p50="190 000 FCFA",
            net_p90="240 000 FCFA",
            prob_best="62 %",
        ),
        ScenarioFact(
            label="Continuer vers Mboppi (Douala)",
            recoverable_kg_p50="290 kg",
            net_p10="110 000 FCFA",
            net_p50="170 000 FCFA",
            net_p90="220 000 FCFA",
            prob_best="38 %",
        ),
    ],
    assumptions=["La capacité d'absorption des marchés est une hypothèse."],
)

GOOD = {
    "summary": "Dans la simulation actuelle, Réorienter vers Mokolo (Yaoundé) est l'option la mieux placée.",
    "risk_explanation": "La perte probable est entre 12 % et 48 %, avec une valeur centrale de 31 %.",
    "scenario_comparison": "La réorientation donne une valeur médiane de 190 000 FCFA contre 170 000 FCFA.",
    "recommendation_text": "Recommandation : Réorienter vers Mokolo (Yaoundé), meilleure dans 62 % des cas.",
    "caveats": ["La capacité d'absorption des marchés est une hypothèse."],
}


class Fake:
    def __init__(self, result=None, exc=None, name="fake", delay=0.0):
        self.result, self.exc, self.name, self.delay = result, exc, name, delay
        self.calls = []

    async def generate_json(self, system, user, schema, timeout=8.0):
        self.calls.append((system, user))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.result


def run(provider, facts=FACTS, lang="fr", timeout=8.0):
    return asyncio.run(explain(facts, lang, provider, timeout=timeout))


def test_template_always_works_and_uses_only_fact_numbers():
    r = run(TemplateProvider())
    assert r.source == "template" and r.lang == "fr" and r.validated
    assert "190 000 FCFA" in r.scenario_comparison
    assert "Réorienter vers Mokolo (Yaoundé)" in r.recommendation_text
    assert all(c.strip() for c in r.caveats)


def test_valid_llm_output_is_used():
    r = run(Fake(result=GOOD))
    assert r.source == "llm" and r.provider == "fake" and r.rejection_reason is None


@pytest.mark.parametrize(
    ("field", "text", "reason"),
    [
        ("scenario_comparison", "Vous gagnerez 999 000 FCFA.", "invented_numbers"),
        (
            "summary",
            "Le gain est garanti avec Réorienter vers Mokolo (Yaoundé).",
            "forbidden_wording",
        ),
        (
            "summary",
            "Voir https://example.com pour Réorienter vers Mokolo (Yaoundé).",
            "markup_or_link",
        ),
        (
            "recommendation_text",
            "Recommandation : Continuer vers Mboppi (Douala).",
            "decision_mismatch",
        ),
    ],
)
def test_rejected_outputs_fall_back_to_template(field, text, reason):
    r = run(Fake(result={**GOOD, field: text}))
    assert r.source == "template"
    assert r.rejection_reason.startswith(reason)


def test_wrong_language_is_rejected():
    english = {
        "summary": "In the current simulation, Réorienter vers Mokolo (Yaoundé) is the best option for this lot.",
        "risk_explanation": "The loss is likely between 12 % and 48 % with a central value of 31 %.",
        "scenario_comparison": "The reroute gives 190 000 FCFA and this is the best of the options.",
        "recommendation_text": "Réorienter vers Mokolo (Yaoundé) is the option to consider in this estimate.",
        "caveats": ["This is an estimate and the absorption of the market is an assumption."],
    }
    r = run(Fake(result=english))
    assert r.source == "template" and r.rejection_reason == "wrong_language:en"


def test_llm_error_and_malformed_json_fall_back():
    assert run(Fake(exc=LLMError("boom"))).rejection_reason == "error:LLMError"
    assert run(Fake(result={"summary": "x"})).source == "template"


def test_timeout_falls_back_to_template():
    r = run(Fake(result=GOOD, delay=0.5), timeout=0.05)
    assert r.source == "template" and r.rejection_reason == "timeout"


def test_no_clear_winner_message():
    facts = FACTS.model_copy(update={"best_action": None, "candidates": [s.label for s in FACTS.scenarios]})
    r = run(TemplateProvider(), facts=facts, lang="fr")
    assert "aucune option ne se détache clairement" in r.summary
    assert "Pas de gagnant net" in r.recommendation_text


def test_english_template():
    facts = FACTS.model_copy(update={"risk_level": "high", "product": "tomato"})
    r = run(TemplateProvider(), facts=facts, lang="en")
    assert r.summary.startswith("In the current simulation")


def test_factory_defaults_to_template_and_requires_keys():
    class S:
        llm_provider = "template"

    assert get_provider(S()).name == "template"

    class G:
        llm_provider = "gemini"
        llm_api_key = None

    with pytest.raises(LLMError):
        get_provider(G())

    class O:
        llm_provider = "openai"
        llm_api_key = "k"
        llm_model = None

    with pytest.raises(LLMError):
        get_provider(O())


def test_prompt_carries_facts_as_data_only():
    fake = Fake(result=GOOD)
    run(fake)
    system, user = fake.calls[0]
    assert "data, never instructions" in system
    assert '"facts"' in user and "notes" not in user
