"""Checks an LLM explanation before it can be shown (design document §34, CA-10).

1. numbers: every number of the text must exist in the facts (French and English formats);
2. decision: the recommended option must be the one of the facts, and no other option may be
   presented as the recommendation;
3. forbidden wording: guarantees and certainty;
4. language: the text must be in the requested language;
5. content: no HTML, no links.

Known limit: it checks numbers and wording, not meaning.
"""

from __future__ import annotations

import re

from .schemas import ExplanationFacts, ExplanationOut, Lang

# Thousands groups ("190 000", "190,000") or plain numbers with optional decimals.
_NUM = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")
_SPACES = re.compile(r"[   ]")
_SMALL_OK = {"1", "2", "3", "4", "5"}  # "option 2", "3 scenarios"...
FORBIDDEN = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bgaranti",
        r"\bcertain(e|ement)?\b",
        r"\bsans risque\b",
        r"\baucun risque\b",
        r"\b100\s?%",
        r"\bguarantee",
        r"\bcertain(ly)?\b",
        r"\brisk[- ]free\b",
        r"\bno risk\b",
        r"\bfor sure\b",
        r"\bassurément\b",
    )
)
# Negated forms are the caveat we want, not a promise.
_NEGATED = re.compile(
    r"\b(n'est pas|pas|aucune|sans|not|no|never|without)\s+(une?\s+|a\s+|any\s+)?"
    r"(garantie|garanti|guarantee|guaranteed|certitude|certainty)\b",
    re.IGNORECASE,
)
_FR_WORDS = {
    "le",
    "la",
    "les",
    "des",
    "est",
    "une",
    "dans",
    "pour",
    "avec",
    "sur",
    "du",
    "et",
    "estimation",
}
_EN_WORDS = {
    "the",
    "is",
    "and",
    "with",
    "for",
    "this",
    "of",
    "to",
    "in",
    "estimate",
    "current",
}
_MARKUP = re.compile(r"<[a-zA-Z/!][^>]*>|https?://|www\.", re.IGNORECASE)


def tokens(text: str) -> set[str]:
    """Normalise every number ("190 000" -> "190000", "3,5" -> "3.5")."""
    return {_SPACES.sub("", m).replace(",", ".") for m in _NUM.findall(text)}


def is_valid(output: str, facts_text: str) -> bool:
    return tokens(output) <= (tokens(facts_text) | _SMALL_OK)


def invented_numbers(output: str, facts_text: str) -> set[str]:
    return tokens(output) - (tokens(facts_text) | _SMALL_OK)


def _text(out: ExplanationOut) -> str:
    return " ".join(
        [
            out.summary,
            out.risk_explanation,
            out.scenario_comparison,
            out.recommendation_text,
            *out.caveats,
        ]
    )


def detect_language(text: str) -> Lang | None:
    words = re.findall(r"[a-zA-Zàâçéèêëîïôûùüÿœ']+", text.lower())
    fr = sum(w in _FR_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    if fr == en:
        return None
    return "fr" if fr > en else "en"


def check(out: ExplanationOut, facts: ExplanationFacts, lang: Lang) -> str | None:
    """Return None when the explanation is acceptable, else the first rejection reason."""
    text = _text(out)
    facts_text = facts.model_dump_json()
    bad = invented_numbers(text, facts_text)
    if bad:
        return f"invented_numbers:{','.join(sorted(bad))[:120]}"
    affirmative = _NEGATED.sub(" ", text)
    for pattern in FORBIDDEN:
        match = pattern.search(affirmative)
        if match and not pattern.search(facts_text):  # a fact may legitimately read "100 %"
            return f"forbidden_wording:{match.group(0).lower()}"
    if _MARKUP.search(text):
        return "markup_or_link"
    detected = detect_language(text)
    if detected is not None and detected != lang:
        return f"wrong_language:{detected}"
    reco = out.recommendation_text.lower()
    labels = [s.label for s in facts.scenarios]
    if facts.best_action:
        if facts.best_action.lower() not in (reco + " " + out.summary.lower()):
            return "decision_mismatch:best_action_missing"
        others = [
            label
            for label in labels
            if label != facts.best_action
            and label.lower() in reco
            and label.lower() not in facts.best_action.lower()
        ]
        if others:
            return "decision_mismatch:other_option_recommended"
    return None
