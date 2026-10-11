from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import Caller, get_caller
from app.repositories import lots as lots_repo
from app.schemas.lot import LotCreate, LotList, LotOut, LotUpdate
from app.services import lot_service

router = APIRouter(tags=["lots"])


@router.post("/lots", response_model=LotOut, status_code=status.HTTP_201_CREATED, summary="Create a lot")
def create_lot(data: LotCreate, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return lot_service.to_out(db, lot_service.create(db, caller, data))


@router.get("/lots", response_model=LotList, summary="List lots (newest first)")
def list_lots(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
              status_: Literal["open", "decided", "closed"] | None = Query(None, alias="status"),
              caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    rows, total = lots_repo.list_(db, caller.organization_id, limit, offset, status_)
    return LotList(items=[lot_service.to_out(db, r) for r in rows], total=total)


@router.get("/lots/{lot_id}", response_model=LotOut, summary="Read a lot with its latest analysis")
def get_lot(lot_id: int, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return lot_service.to_out(db, lot_service.get_or_404(db, caller, lot_id))


@router.patch("/lots/{lot_id}", response_model=LotOut, summary="Update ETA, temperature, price or notes")
def update_lot(lot_id: int, data: LotUpdate, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return lot_service.to_out(db, lot_service.update(db, caller, lot_id, data))
