"""Lots: creation with business validation, reading, editing and their API representation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import Lot
from app.deps import Caller
from app.errors import ApiError, field_error, not_found
from app.repositories import lots as lots_repo
from app.repositories import reference as ref_repo
from app.schemas.common import build
from app.schemas.lot import (
    EnrichmentIn,
    EnrichmentOut,
    LatestAnalysisOut,
    LotCreate,
    LotOut,
    LotUpdate,
)
from app.services import audit, engine, enrichment


def utcnow() -> datetime:
    return datetime.now(UTC)


def hours_between(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds() / 3600.0


def delay_h(lot: Lot) -> float:
    return round(max(0.0, hours_between(lot.eta_current_at, lot.eta_planned_at)), 2)


def create(db: Session, caller: Caller, data: LotCreate) -> Lot:
    engine.params(data.product_code)  # 422 for an unknown product
    if ref_repo.location(db, data.origin_location_id) is None:
        raise field_error("origin_location_id", "unknown", "unknown departure place")
    if ref_repo.market(db, data.destination_market_id) is None:
        raise field_error("destination_market_id", "unknown", "unknown destination market")
    if data.harvested_at > utcnow() + timedelta(hours=1):
        raise field_error("harvested_at", "future_date", "harvest date cannot be in the future")
    lot = Lot(
        organization_id=caller.organization_id,
        created_by=caller.user_id,
        **data.model_dump(),
    )
    db.add(lot)
    db.flush()
    audit.record(
        db,
        "lot_created",
        "lot",
        lot.id,
        organization_id=caller.organization_id,
        user_id=caller.user_id,
    )
    db.commit()
    db.refresh(lot)
    return lot


def get_or_404(db: Session, caller: Caller, lot_id: uuid.UUID) -> Lot:
    lot = lots_repo.get(db, caller.organization_id, lot_id)
    if lot is None:
        raise not_found("Lot")
    return lot


def update(db: Session, caller: Caller, lot_id: uuid.UUID, data: LotUpdate) -> Lot:
    lot = get_or_404(db, caller, lot_id)
    if lot.status == "closed":
        raise ApiError(409, "lot-closed", "This lot is closed.")
    changes = data.model_dump(exclude_unset=True)
    if "eta_current_at" in changes:
        if changes["eta_current_at"] is None:
            raise field_error("eta_current_at", "required", "arrival time cannot be removed")
        if changes["eta_current_at"] <= lot.harvested_at:
            raise field_error("eta_current_at", "invalid", "arrival must be after harvest")
    for key, value in changes.items():
        setattr(lot, key, value)
    audit.record(
        db,
        "lot_updated",
        "lot",
        lot.id,
        organization_id=caller.organization_id,
        user_id=caller.user_id,
        detail={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(lot)
    return lot


def to_out(db: Session, lot: Lot) -> LotOut:
    latest = None
    analysis = lots_repo.latest_analysis(db, lot.id)
    if analysis is not None:
        sim = lots_repo.latest_simulation(db, analysis.id)
        reco = sim.recommendation if sim else None
        best = None
        if sim is not None and reco is not None and reco.best_scenario_id:
            best = next((s for s in sim.scenarios if s.id == reco.best_scenario_id), None)
        latest = build(
            LatestAnalysisOut,
            id=analysis.id,
            analysis_at=analysis.analysis_at,
            risk_level=analysis.risk_level,
            loss_p50=analysis.loss_p50,
            simulation_id=sim.id if sim else None,
            recommended_action=best.action if best else None,
            confidence=reco.confidence if reco else None,
            no_clear_winner=reco.no_clear_winner if reco else None,
        )
    return build(
        LotOut,
        id=lot.id,
        product_code=lot.product_code,
        quantity_kg=lot.quantity_kg,
        harvested_at=lot.harvested_at,
        maturity=lot.maturity,
        packaging=lot.packaging,
        origin_location_id=lot.origin_location_id,
        origin_label=lot.origin.label,
        destination_market_id=lot.destination_market_id,
        destination_name=lot.destination.name,
        destination_city=lot.destination.city,
        eta_planned_at=lot.eta_planned_at,
        eta_current_at=lot.eta_current_at,
        delay_h=delay_h(lot),
        temp_override_c=lot.temp_override_c,
        price_override_fcfa_kg=lot.price_override_fcfa_kg,
        notes=lot.notes,
        status=lot.status,
        created_at=lot.created_at,
        latest_analysis=latest,
    )


def preview_enrichment(db: Session, org_id: uuid.UUID, data: EnrichmentIn) -> EnrichmentOut:
    origin = ref_repo.location(db, data.origin_location_id)
    if origin is None:
        raise field_error("origin_location_id", "unknown", "unknown departure place")
    market = ref_repo.market(db, data.destination_market_id)
    if market is None:
        raise field_error("destination_market_id", "unknown", "unknown destination market")
    leg = enrichment.route(origin, market)
    suggested = data.harvested_at + timedelta(hours=leg.hours) if leg.hours > 0 else None
    end = data.eta_current_at or suggested or data.harvested_at + timedelta(hours=24)
    temp = enrichment.temperature_for(origin, market, data.harvested_at, max(end, utcnow()), None)
    price = enrichment.market_price(market, ref_repo.market_setting(db, org_id, market.id))
    return build(
        EnrichmentOut,
        temperature={"value": temp.mean.value, "source": temp.mean.source},
        temperature_available=temp.automatic,
        diurnal_amp_c={
            "value": temp.half_amplitude.value,
            "source": temp.half_amplitude.source,
        },
        route_km={"value": leg.km, "source": leg.source},
        route_hours={"value": leg.hours, "source": leg.source},
        price_fcfa_kg={"value": price.value, "source": price.source},
        suggested_eta_at=suggested,
    )
