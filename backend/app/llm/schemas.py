"""Data shapes of the explanation layer.

``ExplanationFacts`` only holds values already computed by the engines and formatted by the
backend. The LLM never computes: it rephrases these facts. Free-text lot notes are never part
of the facts (SEC-03).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Lang = Literal["fr", "en"]


class ScenarioFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    recoverable_kg_p50: str
    net_p10: str
    net_p50: str
    net_p90: str
    prob_best: str


class ExplanationFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str
    quantity: str
    risk_level: str
    loss_p10: str
    loss_p50: str
    loss_p90: str
    top_factors: list[str] = Field(default_factory=list)
    scenarios: list[ScenarioFact] = Field(default_factory=list)
    best_action: str | None = None  # None => no clear winner
    confidence: str | None = None
    best_probability: str | None = None
    candidates: list[str] = Field(default_factory=list)  # the two closest options when no clear winner
    reasons: list[str] = Field(default_factory=list)  # deterministic phrases from engine reason codes
    reason_codes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    low_risk: bool = False


class ExplanationOut(BaseModel):
    """The JSON object the LLM must return (design document §34)."""

    model_config = ConfigDict(extra="ignore")

    summary: str = Field(min_length=1, max_length=400)
    risk_explanation: str = Field(min_length=1, max_length=900)
    scenario_comparison: str = Field(min_length=1, max_length=1200)
    recommendation_text: str = Field(min_length=1, max_length=900)
    caveats: list[str] = Field(min_length=1, max_length=8)


class ExplanationResult(ExplanationOut):
    source: Literal["llm", "template"]
    provider: str
    validated: bool
    lang: Lang
    rejection_reason: str | None = None


JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "risk_explanation": {"type": "string"},
        "scenario_comparison": {"type": "string"},
        "recommendation_text": {"type": "string"},
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "risk_explanation",
        "scenario_comparison",
        "recommendation_text",
        "caveats",
    ],
}

# Gemini responseSchema uses the OpenAPI subset with upper-case type names.
GEMINI_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "risk_explanation": {"type": "STRING"},
        "scenario_comparison": {"type": "STRING"},
        "recommendation_text": {"type": "STRING"},
        "caveats": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "summary",
        "risk_explanation",
        "scenario_comparison",
        "recommendation_text",
        "caveats",
    ],
}
