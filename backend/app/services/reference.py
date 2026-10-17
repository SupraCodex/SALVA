"""Reference data, storage sites and the transparency page (/assumptions, FR-22)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Market, MarketSetting, StorageSite
from app.deps import Caller
from app.errors import field_error, not_found
from app.repositories import reference as ref_repo
from app.schemas.common import build
from app.schemas.reference import (
    AssumptionsOut,
    MarketOut,
    MarketSettingIn,
    ProductOut,
    StorageSiteIn,
    StorageSiteOut,
    StorageSiteUpdate,
)
from app.services import audit, engine

LIMITS = [
    "MODEL_LABELS_COME_FROM_A_KINETIC_MODEL_NOT_FIELD_DATA",
    "KINETIC_PARAMETERS_ARE_LITERATURE_RANGES_OR_ASSUMPTIONS",
    "AIR_TEMPERATURE_IS_NOT_PRODUCT_TEMPERATURE",
    "MARKET_ABSORPTION_IS_A_ROUGH_ASSUMPTION",
    "LOSSES_ASSUMED_PROPORTIONAL_TO_QUANTITY",
    "PRICES_INDEPENDENT_BETWEEN_MARKETS",
    "ONE_DECISION_PER_LOT_NO_MULTI_LOT_OPTIMIZATION",
    "FEEDBACK_ONLY_OBSERVES_THE_CHOSEN_ACTION",
    "NOT_A_FOOD_SAFETY_DECISION_TOOL",
]


def products() -> list[ProductOut]:
    doc = engine.products_document()
    out = []
    for code in engine.products():
        entry = doc.get(code, {})
        label = entry.get("label", {})
        out.append(
            build(
                ProductOut,
                code=code,
                label_fr=label.get("fr", code),
                label_en=label.get("en", code),
                source_note=" ".join(str(entry.get("source_note", "")).split()),
            )
        )
    return out


def market_out(m: Market, setting: MarketSetting | None = None) -> MarketOut:
    return build(
        MarketOut,
        id=m.id,
        code=m.code,
        name=m.name,
        city=m.city,
        location_id=m.location_id,
        lat=m.location.lat,
        lon=m.location.lon,
        ref_price_fcfa_kg=m.ref_price_fcfa_kg,
        absorption_kg_day=m.absorption_kg_day,
        assumption_note=m.assumption_note,
        org_price_fcfa_kg=setting.price_fcfa_kg if setting else None,
        org_absorption_kg_day=setting.absorption_kg_day if setting else None,
    )


def markets(db: Session, caller: Caller) -> list[MarketOut]:
    settings = ref_repo.market_settings(db, caller.organization_id)
    return [market_out(m, settings.get(m.id)) for m in ref_repo.markets(db)]


def update_market_setting(
    db: Session, caller: Caller, market_id: uuid.UUID, data: MarketSettingIn
) -> MarketOut:
    market = ref_repo.market(db, market_id)
    if market is None:
        raise not_found("Market")
    setting = ref_repo.market_setting(db, caller.organization_id, market_id)
    if setting is None:
        setting = MarketSetting(organization_id=caller.organization_id, market_id=market_id)
        db.add(setting)
    for key in data.model_fields_set:
        setattr(setting, key, getattr(data, key))
    setting.updated_at = datetime.now(UTC)
    audit.record(
        db,
        "market_setting_updated",
        "market",
        market.id,
        organization_id=caller.organization_id,
        user_id=caller.user_id,
        detail={"fields": sorted(data.model_fields_set)},
    )
    db.commit()
    db.refresh(setting)
    return market_out(market, setting)


def site_out(s: StorageSite) -> StorageSiteOut:
    return build(
        StorageSiteOut,
        id=s.id,
        name=s.name,
        location_id=s.location_id,
        location_label=s.location.label,
        capacity_kg=s.capacity_kg,
        temp_mode=s.temp_mode,
        cost_fcfa_kg_day=s.cost_fcfa_kg_day,
        is_active=s.is_active,
    )


def create_site(db: Session, caller: Caller, data: StorageSiteIn) -> StorageSite:
    if ref_repo.location(db, data.location_id) is None:
        raise field_error("location_id", "unknown", "unknown location")
    site = StorageSite(organization_id=caller.organization_id, **data.model_dump())
    db.add(site)
    db.flush()
    audit.record(
        db,
        "storage_site_created",
        "storage_site",
        site.id,
        organization_id=caller.organization_id,
        user_id=caller.user_id,
    )
    db.commit()
    db.refresh(site)
    return site


def update_site(db: Session, caller: Caller, site_id: uuid.UUID, data: StorageSiteUpdate) -> StorageSite:
    site = ref_repo.storage_site(db, caller.organization_id, site_id)
    if site is None:
        raise not_found("Storage site")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(site, key, value)
    audit.record(
        db,
        "storage_site_updated",
        "storage_site",
        site.id,
        organization_id=caller.organization_id,
        user_id=caller.user_id,
        detail={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(site)
    return site


def assumptions(db: Session, product_code: str = "tomato") -> AssumptionsOut:
    settings = get_settings()
    doc = engine.products_document()
    code = product_code
    p = engine.params(code)
    entries = doc.get(code, {}).get("parameters", {})
    parameters = []
    for name, entry in entries.items():
        parameters.append(
            {
                "name": name,
                "value": entry.get("value"),
                "unit": str(entry.get("unit", "")),
                "description": " ".join(str(entry.get("description", "")).split()),
                "source": str(entry.get("source", "assumption")),
                "reference": entry.get("reference"),
                "note": " ".join(str(entry.get("note", "")).split()) or None,
            }
        )
    economics = [
        {
            "name": "hold_h",
            "value": settings.hold_h,
            "unit": "h",
            "source": "default assumption",
        },
        {
            "name": "transport_fcfa_kg_km",
            "value": settings.transport_fcfa_kg_km,
            "unit": "FCFA/kg/km",
            "source": "default assumption",
        },
        {
            "name": "surplus_price_fraction",
            "value": p.delta,
            "unit": "fraction",
            "source": "products.yaml",
        },
        {
            "name": "sell_local_radius_km",
            "value": settings.sell_local_radius_km,
            "unit": "km",
            "source": "default assumption",
        },
        {
            "name": "road_factor",
            "value": settings.road_factor,
            "unit": "x great-circle",
            "source": "default assumption (fallback distance estimate)",
        },
        {
            "name": "road_speed_kmh",
            "value": settings.road_speed_kmh,
            "unit": "km/h",
            "source": "default assumption (fallback duration estimate)",
        },
        {
            "name": "default_temp_c",
            "value": settings.default_temp_c,
            "unit": "°C",
            "source": "default assumption (used only when the weather service is unavailable)",
        },
        {
            "name": "n_draws",
            "value": settings.n_draws,
            "unit": "draws",
            "source": "design document §32",
        },
        {
            "name": "materiality",
            "value": 0.03,
            "unit": "fraction of lot value",
            "source": "design document §33",
        },
    ]
    model = engine.loss_model(code)
    descriptor = engine.model_descriptor(model)
    registry = engine.registry_info()
    return build(
        AssumptionsOut,
        product=code,
        product_file_sha256=p.file_sha256,
        parameters=parameters,
        economics=economics,
        markets=[market_out(m) for m in ref_repo.markets(db)],
        model={
            "production": descriptor["name"],
            "version": descriptor["version"],
            "fallback": descriptor["fallback"],
            "experimental": registry.get("experimental"),
            "verdict": registry.get("verdict"),
        },
        limits=LIMITS,
    )
