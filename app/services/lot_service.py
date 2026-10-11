from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.db.models import Lot
from app.deps import Caller
from app.errors import ApiError, field_error, not_found
from app.repositories import analyses as analyses_repo
from app.repositories import lots as lots_repo
from app.repositories import reference as ref_repo
from app.schemas.lot import LatestAnalysis, LotCreate, LotOut, LotUpdate
from app.services.common import hours_between, utcnow


def create(db: Session, caller: Caller, data: LotCreate) -> Lot:
    if ref_repo.location(db, data.origin_id) is None:
        raise field_error("origin_id", "unknown", "unknown origin location")
    if ref_repo.market(db, data.destination_id) is None:
        raise field_error("destination_id", "unknown", "unknown destination market")
    if data.harvested_at > utcnow() + timedelta(hours=1):
        raise field_error("harvested_at", "future_date", "harvest date cannot be in the future")
    return lots_repo.save(db, Lot(organization_id=caller.organization_id, **data.model_dump()))


def get_or_404(db: Session, caller: Caller, lot_id: int) -> Lot:
    lot = lots_repo.get(db, caller.organization_id, lot_id)
    if lot is None:
        raise not_found("Lot")
    return lot


def update(db: Session, caller: Caller, lot_id: int, data: LotUpdate) -> Lot:
    lot = get_or_404(db, caller, lot_id)
    if lot.status == "closed":
        raise ApiError(409, "lot-closed", "This lot is closed.")
    changes = data.model_dump(exclude_unset=True)
    if "eta_current" in changes and (changes["eta_current"] is None or changes["eta_current"] <= lot.harvested_at):
        raise field_error("eta_current", "invalid", "arrival must be after harvest")
    for k, v in changes.items():
        setattr(lot, k, v)
    return lots_repo.save(db, lot)


def to_out(db: Session, lot: Lot) -> LotOut:
    a = analyses_repo.latest_for_lot(db, lot.id)
    latest = None
    if a is not None:
        reco = a.recommendation
        action = next((s.action for s in a.scenarios if reco and s.id == reco.scenario_id), None)
        latest = LatestAnalysis(id=a.id, analyzed_at=a.analyzed_at, risk_level=a.risk_level, loss_p50=a.loss_p50,
                                recommended_action=action, confidence=reco.confidence if reco else None)
    return LotOut(
        id=lot.id, product=lot.product, kg=lot.kg, harvested_at=lot.harvested_at, maturity=lot.maturity,
        packaging=lot.packaging, origin_id=lot.origin_id, origin=lot.origin.name, destination_id=lot.destination_id,
        destination=lot.destination.name, eta_planned=lot.eta_planned, eta_current=lot.eta_current,
        delay_h=hours_between(lot.eta_current, lot.eta_planned), temp_override_c=lot.temp_override_c,
        price_override_fcfa_kg=lot.price_override_fcfa_kg, notes=lot.notes, status=lot.status,
        created_at=lot.created_at, latest_analysis=latest)
