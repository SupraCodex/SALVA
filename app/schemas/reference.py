from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Strict


class ProductOut(BaseModel):
    code: str
    label_fr: str
    label_en: str
    source_note: str


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    lat: float
    lon: float


class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location_id: int
    ref_price_fcfa_kg: float
    absorb_kg_day: float
    source: str


class StorageSiteIn(Strict):
    name: str = Field(min_length=2, max_length=120)
    location_id: int
    capacity_kg: float = Field(gt=0, le=1_000_000)
    temp_mode: Literal["ambient_shade", "ventilated", "cold_room"]
    cost_fcfa_kg_day: float = Field(default=0, ge=0, le=10_000)


class StorageSiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location_id: int
    capacity_kg: float
    temp_mode: str
    cost_fcfa_kg_day: float


class ReferenceOut(BaseModel):
    products: list[ProductOut]
    locations: list[LocationOut]
    markets: list[MarketOut]
    storage_sites: list[StorageSiteOut]
