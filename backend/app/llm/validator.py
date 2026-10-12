"""Rejects any generated text containing a number absent from the facts.

Limit (known and accepted): it checks numbers, not meaning.
"""
from __future__ import annotations

import re

# Thousands groups ("190 000") or plain numbers with optional decimals.
_NUM = re.compile(
    r"\d{1,3}(?:[ \u202f\u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
)
_SPACES = re.compile(r"[ \u202f\u00a0]")
_SMALL_OK = {"1", "2", "3", "4", "5"}  # "option 1", "3 scenarios"...


def tokens(text: str) -> set[str]:
    """Normalise every number in `text` ("190 000" -> "190000", "3,5" -> "3.5")."""
    return {_SPACES.sub("", m).replace(",", ".") for m in _NUM.findall(text)}


def is_valid(output: str, facts_text: str) -> bool:
    """True if every number in `output` also appears in `facts_text`."""
    return tokens(output) <= (tokens(facts_text) | _SMALL_OK)


def invented_numbers(output: str, facts_text: str) -> set[str]:
    """Useful for logs/tests: which numbers were not in the facts."""
    return tokens(output) - (tokens(facts_text) | _SMALL_OK)
