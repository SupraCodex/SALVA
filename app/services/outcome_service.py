"""Wave 2: record the decision actually taken and the real result (prediction -> action -> result loop)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Outcome
from app.deps import Caller
from app.errors import ApiError, field_error
from app.repositories import analyses as analyses_repo
from app.schemas.auth import OutcomeIn
from app.services.lot_service import get_or_404 as get_lot_or_404


def record(db: Session, caller: Caller, lot_id: int, data: OutcomeIn) -> Outcome:
    lot = get_lot_or_404(db, caller, lot_id)
    if lot.status == "closed":
        raise ApiError(409, "lot-closed", "This lot is closed.")
    followed = None
    if data.analysis_id is not None:
        a = analyses_repo.get(db, caller.organization_id, data.analysis_id)
        if a is None or a.lot_id != lot.id:
            raise field_error("analysis_id", "unknown", "unknown analysis for this lot")
        reco = a.recommendation
        best = next((s.action for s in a.scenarios if reco and s.id == reco.scenario_id), None)
        followed = (best == data.decision_taken) if best else None
    o = Outcome(lot_id=lot.id, followed_reco=followed, **data.model_dump())
    db.add(o)
    lot.status = "closed" if (data.actual_kg is not None or data.actual_revenue_fcfa is not None) else "decided"
    db.commit()
    db.refresh(o)
    return o
