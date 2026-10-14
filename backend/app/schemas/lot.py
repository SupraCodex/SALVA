from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .common import Out, Sourced, StrictIn

Maturity = Literal["green", "breaker", "ripe"]
Packaging = Literal["crate", "carton", "sack"]
LotStatus = Literal["open", "decided", "closed"]


class LotCreate(StrictIn):
    """The eight fields of the design document's MVP form, plus optional overrides."""

    product_code: str = Field(default="tomato", min_length=1, max_length=40)
    quantity_kg: float = Field(gt=0, le=100_000)
    harvested_at: AwareDatetime
    maturity: Maturity = "breaker"
    packaging: Packaging = "crate"
    origin_location_id: uuid.UUID
    destination_market_id: uuid.UUID
    eta_planned_at: AwareDatetime
    eta_current_at: AwareDatetime | None = None
    temp_override_c: float | None = Field(default=None, ge=0, le=50)
    price_override_fcfa_kg: float | None = Field(default=None, gt=0, le=100_000)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _temporal_consistency(self) -> LotCreate:
        if self.eta_current_at is None:
            self.eta_current_at = self.eta_planned_at
        if self.eta_planned_at <= self.harvested_at:
            raise ValueError("eta_planned_at must be after harvested_at")
        if self.eta_current_at <= self.harvested_at:
            raise ValueError("eta_current_at must be after harvested_at")
        if self.eta_current_at - self.harvested_at > timedelta(days=30):
            raise ValueError("a lot older than 30 days at arrival is outside the model's domain")
        return self


class LotUpdate(StrictIn):
    eta_current_at: AwareDatetime | None = None
    temp_override_c: float | None = Field(default=None, ge=0, le=50)
    price_override_fcfa_kg: float | None = Field(default=None, gt=0, le=100_000)
    notes: str | None = Field(default=None, max_length=500)


class LatestAnalysisOut(Out):
    id: uuid.UUID
    analysis_at: datetime
    risk_level: str
    loss_p50: float
    simulation_id: uuid.UUID | None = None
    recommended_action: str | None = None
    confidence: str | None = None
    no_clear_winner: bool | None = None


class LotOut(Out):
    id: uuid.UUID
    product_code: str
    quantity_kg: float
    harvested_at: datetime
    maturity: Maturity
    packaging: Packaging
    origin_location_id: uuid.UUID
    origin_label: str
    destination_market_id: uuid.UUID
    destination_name: str
    destination_city: str
    eta_planned_at: datetime
    eta_current_at: datetime
    delay_h: float
    temp_override_c: float | None
    price_override_fcfa_kg: float | None
    notes: str | None
    status: LotStatus
    created_at: datetime
    latest_analysis: LatestAnalysisOut | None = None


class LotCreated(Out):
    id: uuid.UUID
    status: LotStatus
    delay_h: float
    created_at: datetime


class LotList(Out):
    items: list[LotOut]
    next_cursor: str | None


class EnrichmentIn(StrictIn):
    origin_location_id: uuid.UUID
    destination_market_id: uuid.UUID
    harvested_at: AwareDatetime
    eta_current_at: AwareDatetime | None = None


class EnrichmentOut(Out):
    temperature: Sourced
    temperature_available: bool
    diurnal_amp_c: Sourced
    route_km: Sourced
    route_hours: Sourced
    price_fcfa_kg: Sourced
    suggested_eta_at: datetime | None
