"""Wave 2: feedback loop."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import Caller, get_caller
from app.repositories import lots as lots_repo
from app.schemas.auth import OutcomeIn, OutcomeOut
from app.services import lot_service, outcome_service

router = APIRouter(tags=["outcomes (wave 2)"])


@router.post("/lots/{lot_id}/outcomes", response_model=OutcomeOut, status_code=status.HTTP_201_CREATED,
             summary="Record the decision taken and, later, the real result")
def record(lot_id: int, data: OutcomeIn, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return outcome_service.record(db, caller, lot_id, data)


@router.get("/lots/{lot_id}/outcomes", response_model=list[OutcomeOut], summary="Outcomes of a lot")
def list_outcomes(lot_id: int, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    lot = lot_service.get_or_404(db, caller, lot_id)
    return lots_repo.outcomes(db, lot.id)
