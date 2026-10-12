"""Data shapes shared by the LLM layer.

`ExplanationFacts` holds ONLY values already computed and formatted by the
engine (core/ + services). The LLM never computes anything: it rephrases.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Lang = Literal["fr", "en"]


class ScenarioFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str  # e.g. "Reroute to Douala"
    net_p10: str  # e.g. "120 000 FCFA"
    net_p50: str
    net_p90: str
    prob_best: str | None = None  # e.g. "62 %"


class ExplanationFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str  # "tomate" / "tomato"
    risk_level: str  # "low" | "medium" | "high"
    loss_p10: str  # "12 %"
    loss_p50: str
    loss_p90: str
    best_action: str | None = None  # None => no clear winner
    confidence: str | None = None  # "62 %"
    scenarios: list[ScenarioFact] = []
    assumptions: list[str] = []  # e.g. "Temperature: assumption (28 °C)"


class ExplanationOut(BaseModel):
    summary: str
    risk: str
    scenarios: str
    caveats: str


class ExplanationResult(ExplanationOut):
    source: Literal["llm", "template"]
    lang: Lang


# Gemini responseSchema (OpenAPI subset, upper-case types).
GEMINI_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "risk": {"type": "STRING"},
        "scenarios": {"type": "STRING"},
        "caveats": {"type": "STRING"},
    },
    "required": ["summary", "risk", "scenarios", "caveats"],
}
