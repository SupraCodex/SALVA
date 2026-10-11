from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import Caller, get_caller
from app.rate_limit import limit_by_ip
from app.schemas.analysis import AnalysisOut, AnalyzeIn
from app.services import analysis_service

router = APIRouter(tags=["analyses"])


@router.post("/lots/{lot_id}/analyze", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(limit_by_ip)],
             summary="Risk + simulation + allocation + recommendation in one call; result stored")
def analyze(lot_id: int, body: AnalyzeIn | None = None, caller: Caller = Depends(get_caller),
            db: Session = Depends(get_db)):
    return analysis_service.to_out(analysis_service.analyze(db, caller, lot_id, body or AnalyzeIn()))


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut, summary="Read a stored analysis")
def get_analysis(analysis_id: int, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return analysis_service.to_out(analysis_service.get_or_404(db, caller, analysis_id))
