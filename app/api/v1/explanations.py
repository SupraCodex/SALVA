from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import Caller, get_caller
from app.rate_limit import limit_by_ip
from app.schemas.analysis import ExplanationIn, ExplanationOut
from app.services import explanation_service

router = APIRouter(tags=["explanations"])


@router.post("/analyses/{analysis_id}/explanation", response_model=ExplanationOut,
             dependencies=[Depends(limit_by_ip)],
             summary="Plain-language explanation: validated LLM, else template. Always 200.")
async def explain(analysis_id: int, body: ExplanationIn | None = None, caller: Caller = Depends(get_caller),
                  db: Session = Depends(get_db)):
    lang = body.lang if body else caller.locale
    return explanation_service.to_out(await explanation_service.explain(db, caller, analysis_id, lang))
