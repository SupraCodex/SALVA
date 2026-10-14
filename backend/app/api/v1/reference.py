from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import Caller, get_caller, require_admin
from app.errors import field_error
from app.repositories import reference as ref_repo
from app.schemas.reference import (
    AssumptionsOut,
    LocationOut,
    MarketOut,
    ProductOut,
    RouteEstimateOut,
    StorageSiteIn,
    StorageSiteOut,
    StorageSiteUpdate,
)
from app.services import enrichment
from app.services import reference as ref_service

router = APIRouter(tags=["reference"])


@router.get("/products", response_model=list[ProductOut], summary="Available products")
def products(_: Caller = Depends(get_caller)):
    return ref_service.products()


@router.get(
    "/locations",
    response_model=list[LocationOut],
    summary="Departure places and storage relays",
)
def locations(_: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return ref_repo.locations(db)


@router.get(
    "/markets",
    response_model=list[MarketOut],
    summary="Markets with reference price and absorption",
)
def markets(_: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return [ref_service.market_out(m) for m in ref_repo.markets(db)]


@router.get(
    "/routes/estimate",
    response_model=RouteEstimateOut,
    summary="Road distance and duration estimate",
)
def route_estimate(
    origin_location_id: uuid.UUID = Query(...),
    market_id: uuid.UUID = Query(...),
    _: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    origin = ref_repo.location(db, origin_location_id)
    market = ref_repo.market(db, market_id)
    if origin is None:
        raise field_error("origin_location_id", "unknown", "unknown departure place")
    if market is None:
        raise field_error("market_id", "unknown", "unknown market")
    leg = enrichment.route(origin, market)
    return RouteEstimateOut(km=leg.km, hours=leg.hours, source=leg.source)


@router.get(
    "/assumptions",
    response_model=AssumptionsOut,
    summary="Model parameters, sources and limits",
)
def assumptions(_: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return ref_service.assumptions(db)


@router.get(
    "/storage-sites",
    response_model=list[StorageSiteOut],
    summary="Storage sites of the organization",
)
def storage_sites(caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return [ref_service.site_out(s) for s in ref_repo.storage_sites(db, caller.organization_id)]


@router.post(
    "/storage-sites",
    response_model=StorageSiteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a storage site (administrator)",
)
def create_storage_site(
    data: StorageSiteIn,
    caller: Caller = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ref_service.site_out(ref_service.create_site(db, caller, data))


@router.patch(
    "/storage-sites/{site_id}",
    response_model=StorageSiteOut,
    summary="Edit or deactivate a storage site (administrator)",
)
def update_storage_site(
    site_id: uuid.UUID,
    data: StorageSiteUpdate,
    caller: Caller = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ref_service.site_out(ref_service.update_site(db, caller, site_id, data))
