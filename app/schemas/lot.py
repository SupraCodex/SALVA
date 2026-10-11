from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .common import Strict


class LotCreate(Strict):
    product: Literal["tomato"]
    kg: float = Field(gt=0, le=100_000)
    harvested_at: AwareDatetime
    maturity: Literal["green", "breaker", "ripe"]
    packaging: Literal["crate", "carton", "sack"]
    origin_id: int
    destination_id: int
    eta_current: AwareDatetime
    eta_planned: AwareDatetime | None = Field(None, description="Defaults to eta_current (no delay)")
    temp_override_c: float | None = Field(None, ge=-5, le=55)
    price_override_fcfa_kg: float | None = Field(None, gt=0, le=1_000_000)
    notes: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _dates(self):
        if self.eta_planned is None:
            self.eta_planned = self.eta_current
        if self.eta_current <= self.harvested_at or self.eta_planned <= self.harvested_at:
            raise ValueError("arrival must be after harvest")
        return self


class LotUpdate(Strict):
    eta_current: AwareDatetime | None = None
    temp_override_c: float | None = Field(None, ge=-5, le=55)
    price_override_fcfa_kg: float | None = Field(None, gt=0, le=1_000_000)
    notes: str | None = Field(None, max_length=500)


class LatestAnalysis(BaseModel):
    id: int
    analyzed_at: datetime
    risk_level: str
    loss_p50: float
    recommended_action: str | None
    confidence: str | None


class LotOut(BaseModel):
    id: int
    product: str
    kg: float
    harvested_at: datetime
    maturity: str
    packaging: str
    origin_id: int
    origin: str
    destination_id: int
    destination: str
    eta_planned: datetime
    eta_current: datetime
    delay_h: float
    temp_override_c: float | None
    price_override_fcfa_kg: float | None
    notes: str | None
    status: str
    created_at: datetime
    latest_analysis: LatestAnalysis | None = None


class LotList(BaseModel):
    items: list[LotOut]
    total: int
