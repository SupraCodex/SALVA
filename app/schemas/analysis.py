from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from .common import Quantiles, Strict


class AnalyzeIn(Strict):
    now: AwareDatetime | None = Field(None, description="Replay mode: analyse as if it were this time")
    n_draws: int | None = Field(None, ge=100, le=20000)
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    risk_profile: Literal["prudent", "balanced", "ambitious"] = "balanced"
    absorb_override: dict[int, float] | None = Field(None, description="market_id -> kg/day")


class Factor(BaseModel):
    name: str
    contribution: float
    direction: Literal["increases_risk", "decreases_risk", "neutral"]


class Risk(BaseModel):
    level: Literal["low", "medium", "high"]
    loss: Quantiles
    factors: list[Factor]


class AllocationItem(BaseModel):
    action: str
    kg: float
    market_id: int | None = None
    market: str | None = None
    site_id: int | None = None
    site: str | None = None
    extra_h: float = 0.0
    cost_per_kg: float = 0.0


class ScenarioOut(BaseModel):
    id: int
    key: str
    action: str
    feasible: bool
    infeasible_reason: str | None
    allocation: list[AllocationItem]
    kg_equiv: Quantiles | None
    net_value_fcfa: Quantiles | None
    prob_best: float


class RecommendationOut(BaseModel):
    scenario_id: int | None
    action: str | None
    confidence: Literal["high", "medium", "low", "none"]
    tied_scenario_ids: list[int]
    rationale: list[str]
    risk_profile: str


class Assumption(BaseModel):
    name: str
    value: float | str | None
    source: str


class ModelInfo(BaseModel):
    version: str
    fallback: bool


class AnalysisOut(BaseModel):
    id: int
    lot_id: int
    analyzed_at: datetime
    model: ModelInfo
    seed: int
    n_draws: int
    risk: Risk
    scenarios: list[ScenarioOut]
    recommendation: RecommendationOut | None
    assumptions: list[Assumption]
    disclaimer_code: str = "MODEL_ESTIMATE_NOT_FIELD_VALIDATED"


class ExplanationIn(Strict):
    lang: Literal["fr", "en"] = "fr"


class ExplanationOut(BaseModel):
    id: int
    analysis_id: int
    lang: str
    source: Literal["template", "llm"]
    provider: str | None
    validated: bool
    summary: str
    risk: str
    scenarios: str
    caveats: list[str]
