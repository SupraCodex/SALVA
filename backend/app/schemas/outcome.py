from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import DISCLAIMER_CODE, Out, StrictIn

Decision = Literal["continue", "store", "reroute", "sell_local", "optimized_split", "other"]


class ExplanationIn(StrictIn):
    lang: Literal["fr", "en"] | None = None


class ExplanationOut(Out):
    id: uuid.UUID
    recommendation_id: uuid.UUID
    lang: Literal["fr", "en"]
    source: Literal["llm", "template"]
    provider: str | None
    validated: bool
    summary: str
    risk_explanation: str
    scenario_comparison: str
    recommendation_text: str
    caveats: list[str]
    disclaimer_code: str = DISCLAIMER_CODE
    created_at: datetime


class OutcomeIn(StrictIn):
    simulation_id: uuid.UUID | None = None
    scenario_id: uuid.UUID | None = None
    decision_taken: Decision
    actual_recovered_kg: float | None = Field(default=None, ge=0, le=100_000)
    actual_revenue_fcfa: float | None = Field(default=None, ge=0, le=1e10)


class OutcomeOut(Out):
    id: uuid.UUID
    lot_id: uuid.UUID
    simulation_run_id: uuid.UUID | None
    scenario_id: uuid.UUID | None
    decision_taken: str
    followed_reco: bool | None
    actual_recovered_kg: float | None
    actual_revenue_fcfa: float | None
    recorded_at: datetime


class SimulationSummaryOut(Out):
    id: uuid.UUID
    created_at: datetime
    risk_profile: str
    n_draws: int
    seed: int
    best_action: str | None
    best_scenario_key: str | None
    confidence: str
    no_clear_winner: bool
    user_overrides: int


class AnalysisSummaryOut(Out):
    id: uuid.UUID
    analysis_at: datetime
    replay: bool
    risk_level: str
    loss_p10: float
    loss_p50: float
    loss_p90: float
    model_version: str
    simulations: list[SimulationSummaryOut]


class LotHistoryOut(Out):
    lot_id: uuid.UUID
    analyses: list[AnalysisSummaryOut]
    outcomes: list[OutcomeOut]
