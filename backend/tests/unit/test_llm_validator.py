from app.llm.validator import detect_language, invented_numbers, is_valid, tokens

FACTS = '{"net": "190 000 FCFA", "loss": "31 %", "prob": "62 %", "en": "190,000 FCFA"}'


def test_tokens_normalise_thousands_and_decimals():
    assert tokens("190 000 FCFA") == {"190000"}
    assert tokens("190 000 FCFA") == {"190000"}
    assert tokens("3,5 %") == {"3.5"}
    assert tokens("0,31") == {"0.31"}


def test_text_with_facts_numbers_is_valid():
    assert is_valid("Valeur de 190 000 FCFA, perte de 31 %.", FACTS)


def test_invented_number_is_rejected():
    text = "Vous gagnerez 250 000 FCFA."
    assert not is_valid(text, FACTS)
    assert invented_numbers(text, FACTS) == {"250000"}


def test_small_numbers_are_tolerated():
    assert is_valid("Option 2 sur 3.", FACTS)


def test_reformatted_number_is_rejected_conservatively():
    assert is_valid("190000 FCFA", FACTS)
    # English thousands separator is accepted only if the facts use the same format.
    assert is_valid("190,000 FCFA", FACTS)
    assert not is_valid("190.5 FCFA", FACTS)


def test_language_detection():
    assert detect_language("Dans la simulation actuelle, la perte est estimée pour le lot.") == "fr"
    assert detect_language("In the current simulation the loss is an estimate for this lot.") == "en"


def test_negated_guarantee_is_allowed_but_promise_is_not():
    from app.llm.schemas import ExplanationFacts, ExplanationOut
    from app.llm.validator import check

    facts = ExplanationFacts(
        product="tomate",
        quantity="500 kg",
        risk_level="élevé",
        loss_p10="1 %",
        loss_p50="2 %",
        loss_p90="3 %",
    )
    base = {
        "summary": "Dans la simulation actuelle, la perte est une estimation pour le lot.",
        "risk_explanation": "La perte est estimée pour le lot.",
        "scenario_comparison": "Les options sont proches dans la simulation.",
        "recommendation_text": "Aucune option ne se détache pour le lot.",
        "caveats": ["Ce n'est pas une garantie."],
    }
    assert check(ExplanationOut(**base), facts, "fr") is None
    promise = {
        **base,
        "summary": "Le résultat est garanti pour le lot dans la simulation.",
    }
    assert check(ExplanationOut(**promise), facts, "fr").startswith("forbidden_wording")
