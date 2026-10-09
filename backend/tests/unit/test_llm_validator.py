from app.llm.validator import invented_numbers, is_valid, tokens

FACTS = '{"net": "190 000 FCFA", "loss": "31 %", "prob": "62 %"}'


def test_tokens_normalise_thousands_and_decimals():
    assert tokens("190 000 FCFA") == {"190000"}
    assert tokens("190\u202f000 FCFA") == {"190000"}
    assert tokens("3,5 %") == {"3.5"}


def test_text_with_facts_numbers_is_valid():
    assert is_valid("Valeur de 190 000 FCFA, perte de 31 %.", FACTS)


def test_invented_number_is_rejected():
    text = "Vous gagnerez 250 000 FCFA."
    assert not is_valid(text, FACTS)
    assert invented_numbers(text, FACTS) == {"250000"}


def test_small_numbers_are_tolerated():
    assert is_valid("Option 2 sur 3.", FACTS)


def test_reformatted_number_is_rejected():
    # "190000" == "190 000" after normalisation => accepted
    assert is_valid("190000 FCFA", FACTS)
    # "190,000" is read as 190.000 => rejected (conservative, falls back)
    assert not is_valid("190,000 FCFA", FACTS)
