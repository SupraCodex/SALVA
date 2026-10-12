import asyncio

from app.llm.explain import explain
from app.llm.provider import LLMError
from app.llm.providers import get_provider
from app.llm.providers.template import TemplateProvider
from app.llm.schemas import ExplanationFacts, ScenarioFact

FACTS = ExplanationFacts(
    product="tomate",
    risk_level="high",
    loss_p10="12 %",
    loss_p50="31 %",
    loss_p90="48 %",
    best_action="Réorienter vers Douala",
    confidence="62 %",
    scenarios=[
        ScenarioFact(
            label="Réorienter vers Douala",
            net_p10="120 000 FCFA",
            net_p50="190 000 FCFA",
            net_p90="240 000 FCFA",
            prob_best="62 %",
        )
    ],
    assumptions=["Température : hypothèse (28 °C)"],
)

GOOD = {
    "summary": "Réorienter vers Douala est l'option la mieux placée (62 %).",
    "risk": "Perte estimée entre 12 % et 48 %, centrale 31 %.",
    "scenarios": "Valeur médiane de 190 000 FCFA.",
    "caveats": "Température : hypothèse (28 °C). Estimation, pas une garantie.",
}


class Fake:
    name = "fake"

    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    async def generate_json(self, system, user, schema, timeout=8.0):
        if self.exc:
            raise self.exc
        return self.result


def run(provider):
    return asyncio.run(explain(FACTS, "fr", provider))


def test_template_always_works():
    r = run(TemplateProvider())
    assert r.source == "template" and r.lang == "fr"
    assert "190 000 FCFA" in r.scenarios


def test_valid_llm_output_is_used():
    r = run(Fake(result=GOOD))
    assert r.source == "llm"


def test_invented_number_falls_back_to_template():
    bad = {**GOOD, "scenarios": "Vous gagnerez 999 000 FCFA."}
    assert run(Fake(result=bad)).source == "template"


def test_llm_error_falls_back_to_template():
    assert run(Fake(exc=LLMError("boom"))).source == "template"


def test_timeout_falls_back_to_template():
    assert run(Fake(exc=TimeoutError())).source == "template"


def test_malformed_json_falls_back_to_template():
    assert run(Fake(result={"summary": "x"})).source == "template"


def test_no_clear_winner_message():
    facts = FACTS.model_copy(update={"best_action": None, "confidence": None})
    r = asyncio.run(explain(facts, "en", TemplateProvider()))
    assert "No option clearly stands out" in r.summary


def test_factory_defaults_to_template():
    class S:
        llm_provider = "template"

    assert get_provider(S()).name == "template"


def test_reason_codes_are_optional_and_kept():
    assert FACTS.reason_codes == []
    facts = FACTS.model_copy(update={"reason_codes": ["long_delay"]})
    assert "long_delay" in facts.model_dump_json()
