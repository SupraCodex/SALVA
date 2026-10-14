from __future__ import annotations

import binascii
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import Caller, get_caller, limit_compute
from app.errors import field_error
from app.repositories import lots as lots_repo
from app.schemas.analysis import AnalysisCreate, AnalysisOut
from app.schemas.lot import (
    EnrichmentIn,
    EnrichmentOut,
    LotCreate,
    LotList,
    LotOut,
    LotUpdate,
)
from app.schemas.outcome import LotHistoryOut, OutcomeIn, OutcomeOut
from app.services import analysis as analysis_service
from app.services import lots as lot_service
from app.services import outcomes as outcome_service

router = APIRouter(tags=["lots"])


@router.post(
    "/lots",
    response_model=LotOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lot",
)
def create_lot(data: LotCreate, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return lot_service.to_out(db, lot_service.create(db, caller, data))


@router.get(
    "/lots",
    response_model=LotList,
    summary="List lots, newest first (cursor pagination)",
)
def list_lots(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, max_length=200),
    status_: Literal["open", "decided", "closed"] | None = Query(None, alias="status"),
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    try:
        rows, next_cursor = lots_repo.list_(db, caller.organization_id, limit, cursor, status_)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise field_error("cursor", "invalid", "invalid pagination cursor") from None
    return LotList(items=[lot_service.to_out(db, r) for r in rows], next_cursor=next_cursor)


@router.post(
    "/lots/enrichment-preview",
    response_model=EnrichmentOut,
    summary="Automatic temperature, route and price before creating a lot",
)
def enrichment_preview(
    data: EnrichmentIn,
    _: Caller = Depends(limit_compute),
    db: Session = Depends(get_db),
):
    return lot_service.preview_enrichment(db, data)


@router.get(
    "/lots/{lot_id}",
    response_model=LotOut,
    summary="Read a lot with its latest analysis",
)
def get_lot(
    lot_id: uuid.UUID,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    return lot_service.to_out(db, lot_service.get_or_404(db, caller, lot_id))


@router.patch(
    "/lots/{lot_id}",
    response_model=LotOut,
    summary="Update ETA, temperature, price or notes",
)
def update_lot(
    lot_id: uuid.UUID,
    data: LotUpdate,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    return lot_service.to_out(db, lot_service.update(db, caller, lot_id, data))


@router.post(
    "/lots/{lot_id}/analyses",
    response_model=AnalysisOut,
    status_code=status.HTTP_201_CREATED,
    summary="Run a risk analysis (optionally replayed at a chosen date)",
)
def create_analysis(
    lot_id: uuid.UUID,
    body: AnalysisCreate | None = None,
    caller: Caller = Depends(limit_compute),
    db: Session = Depends(get_db),
):
    return analysis_service.to_out(analysis_service.analyze(db, caller, lot_id, body or AnalysisCreate()))


@router.get(
    "/lots/{lot_id}/history",
    response_model=LotHistoryOut,
    summary="Analyses, simulations, decisions and results of a lot",
)
def history(
    lot_id: uuid.UUID,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    return outcome_service.history(db, caller, lot_id)


@router.post(
    "/lots/{lot_id}/outcomes",
    response_model=OutcomeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record the decision taken and, later, the real result",
)
def record_outcome(
    lot_id: uuid.UUID,
    data: OutcomeIn,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    return outcome_service.record(db, caller, lot_id, data)
