from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field

from .common import Out, StrictIn

TempMode = Literal["ambient_shade", "ventilated", "cold_room"]


class ProductOut(Out):
    code: str
    label_fr: str
    label_en: str
    source_note: str


class LocationOut(Out):
    id: uuid.UUID
    code: str
    label: str
    kind: str
    lat: float
    lon: float
    source_note: str


class MarketOut(Out):
    id: uuid.UUID
    code: str
    name: str
    city: str
    location_id: uuid.UUID
    lat: float
    lon: float
    ref_price_fcfa_kg: float
    absorption_kg_day: float
    assumption_note: str
    org_price_fcfa_kg: float | None = None
    org_absorption_kg_day: float | None = None


class MarketSettingIn(StrictIn):
    """Organization values for a market; null restores the reference value."""

    price_fcfa_kg: float | None = Field(default=None, gt=0, le=100_000)
    absorption_kg_day: float | None = Field(default=None, ge=0, le=1_000_000)


class StorageSiteIn(StrictIn):
    name: str = Field(min_length=2, max_length=120)
    location_id: uuid.UUID
    capacity_kg: float = Field(gt=0, le=1_000_000)
    temp_mode: TempMode
    cost_fcfa_kg_day: float = Field(default=0.0, ge=0, le=10_000)


class StorageSiteUpdate(StrictIn):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    capacity_kg: float | None = Field(default=None, gt=0, le=1_000_000)
    temp_mode: TempMode | None = None
    cost_fcfa_kg_day: float | None = Field(default=None, ge=0, le=10_000)
    is_active: bool | None = None


class StorageSiteOut(Out):
    id: uuid.UUID
    name: str
    location_id: uuid.UUID
    location_label: str
    capacity_kg: float
    temp_mode: str
    cost_fcfa_kg_day: float
    is_active: bool


class RouteEstimateOut(Out):
    km: float
    hours: float
    source: str


class ParameterOut(Out):
    name: str
    value: Any
    unit: str
    description: str
    source: str
    reference: str | None = None
    note: str | None = None


class EconomicAssumptionOut(Out):
    name: str
    value: float
    unit: str
    source: str


class ModelInfoOut(Out):
    production: str
    version: str
    fallback: bool
    experimental: str | None
    verdict: str | None


class AssumptionsOut(Out):
    product: str
    product_file_sha256: str
    parameters: list[ParameterOut]
    economics: list[EconomicAssumptionOut]
    markets: list[MarketOut]
    model: ModelInfoOut
    limits: list[str]
