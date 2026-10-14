from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, Field

from .common import DISCLAIMER_CODE, Out, Quantiles, StrictIn

RiskProfile = Literal["prudent", "balanced", "ambitious"]


class AnalysisCreate(StrictIn):
    analysis_at: AwareDatetime | None = None  # replay mode (FR-16)


class ModelOut(Out):
    name: str
    version: str
    fallback: bool


class FactorOut(Out):
    name: str
    contribution: float
    direction: Literal["increases_risk", "decreases_risk", "neutral"]


class RiskOut(Out):
    level: Literal["low", "medium", "high"]
    loss_fraction: Quantiles
    interval_width: float
    loss_reason: str
    uncertainty_reason: str


class AnalysisOut(Out):
    id: uuid.UUID
    lot_id: uuid.UUID
    analysis_at: datetime
    replay: bool
    model: ModelOut
    inputs: dict[str, Any]
    risk: RiskOut
    top_factors: list[FactorOut]
    shelf_life_p50_h: float | None
    extrapolated_features: list[str]
    disclaimer_code: str = DISCLAIMER_CODE
    created_at: datetime


class MarketOverride(StrictIn):
    price_fcfa_kg: float | None = Field(default=None, gt=0, le=100_000)
    absorption_kg: float | None = Field(default=None, ge=0, le=1_000_000)


class SimulationAssumptionsIn(StrictIn):
    markets: dict[uuid.UUID, MarketOverride] = Field(default_factory=dict, max_length=50)
    hold_h: float | None = Field(default=None, ge=1, le=72)
    transport_fcfa_kg_km: float | None = Field(default=None, ge=0, le=10)
    surplus_price_fraction: float | None = Field(default=None, ge=0, le=1)


class SimulationCreate(StrictIn):
    n_draws: int | None = Field(default=None, ge=100, le=20_000)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    risk_profile: RiskProfile = "balanced"
    assumptions: SimulationAssumptionsIn = Field(default_factory=SimulationAssumptionsIn)


class AssumptionOut(Out):
    key: str
    value: float | str | None
    unit: str
    source: str
    user_override: bool = False


class AllocationLineOut(Out):
    scenario_key: str
    action: str
    label: dict[str, str]
    kg: float
    full_price_kg: float
    surplus_kg: float


class ScenarioOut(Out):
    id: uuid.UUID
    key: str
    action: str
    label: dict[str, str]
    market_id: uuid.UUID | None
    storage_site_id: uuid.UUID | None
    feasible: bool
    infeasible_reason: str | None
    discouraged: bool
    discouraged_reason: str | None
    loss: Quantiles
    recoverable_kg: Quantiles
    gross_value_fcfa: Quantiles
    net_value_fcfa: Quantiles
    prob_best: float
    risk_level: str | None
    allocation: list[AllocationLineOut]
    discarded_kg: float
    storage_used_kg: float
    extra_h: float
    hold_h: float
    transit_saving_h: float
    cost_p50_fcfa: float
    extrapolation_warnings: list[str]


class RecommendationOut(Out):
    id: uuid.UUID
    simulation_id: uuid.UUID
    best_scenario_id: uuid.UUID | None
    best_scenario_key: str | None
    best_action: str | None
    confidence: Literal["high", "medium", "low", "none"]
    no_clear_winner: bool
    prob_best: float
    gap_fraction: float | None
    rationale_codes: list[str]
    ranked_scenario_ids: list[uuid.UUID]
    candidate_scenario_ids: list[uuid.UUID]
    low_risk: bool
    policy: dict[str, Any]
    assumption_codes: list[str]
    disclaimer_code: str = DISCLAIMER_CODE


class SimulationOut(Out):
    id: uuid.UUID
    analysis_id: uuid.UUID
    lot_id: uuid.UUID
    n_draws: int
    seed: int
    risk_profile: RiskProfile
    duration_ms: float
    assumptions: list[AssumptionOut]
    scenarios: list[ScenarioOut]
    recommendation: RecommendationOut
    disclaimer_code: str = DISCLAIMER_CODE
    created_at: datetime


class SensitivityIn(StrictIn):
    temperatures_c: list[float] | None = Field(default=None, min_length=2, max_length=7)
    delays_h: list[float] | None = Field(default=None, min_length=2, max_length=7)


class SensitivityPointOut(Out):
    temp_c: float
    delay_h: float
    best_scenario_key: str | None
    best_action: str | None
    confidence: str


class SensitivityTransitionOut(Out):
    axis: Literal["temperature", "delay"]
    from_value: float
    to_value: float
    fixed_value: float
    from_action: str | None
    to_action: str | None


class SensitivityOut(Out):
    simulation_id: uuid.UUID
    n_draws: int
    seed: int
    current: dict[str, float]
    temperatures_c: list[float]
    delays_h: list[float]
    points: list[SensitivityPointOut]
    transitions: list[SensitivityTransitionOut]
    disclaimer_code: str = DISCLAIMER_CODE


QuestionKind = Literal[
    "what_if", "risk", "recommendation", "why", "uncertainty", "assumptions", "unsupported"
]


class QuestionIn(StrictIn):
    """A question about one analysis (FR-18). Free text, never sent to a language model."""

    question: str = Field(min_length=3, max_length=300)
    lang: Literal["fr", "en"] = "fr"
    simulation_id: uuid.UUID | None = None


class WhatIfOut(Out):
    changes: dict[str, Any]
    best_label: dict[str, str] | None
    best_action: str | None
    confidence: str
    no_clear_winner: bool
    net_value_fcfa: Quantiles
    loss_fraction: Quantiles
    current_best_label: dict[str, str] | None
    current_net_p50_fcfa: float | None


class QuestionOut(Out):
    kind: QuestionKind
    answer: str
    what_if: WhatIfOut | None = None
    disclaimer_code: str = DISCLAIMER_CODE
