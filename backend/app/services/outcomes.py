"""Feedback loop (FR-15, CA-15): decision actually taken and, later, the real result.

Outcomes are stored apart from the synthetic training data (DAT-04). They only show the
result of the action taken (selection bias), so they serve calibration, not naive training.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import Outcome
from app.deps import Caller
from app.errors import ApiError, field_error
from app.repositories import lots as lots_repo
from app.schemas.outcome import (
    AnalysisSummaryOut,
    LotHistoryOut,
    OutcomeIn,
    SimulationSummaryOut,
)
from app.services import audit
from app.services.lots import get_or_404 as get_lot_or_404


def record(db: Session, caller: Caller, lot_id: uuid.UUID, data: OutcomeIn) -> Outcome:
    lot = get_lot_or_404(db, caller, lot_id)
    if lot.status == "closed":
        raise ApiError(409, "lot-closed", "This lot is closed.")
    followed = None
    scenario_id = data.scenario_id
    run_id = data.simulation_id
    if run_id is not None:
        run = lots_repo.simulation(db, caller.organization_id, run_id)
        if run is None or run.analysis.lot_id != lot.id:
            raise field_error("simulation_id", "unknown", "unknown simulation for this lot")
        reco = run.recommendation
        best = next((s for s in run.scenarios if reco and s.id == reco.best_scenario_id), None)
        if scenario_id is not None and all(s.id != scenario_id for s in run.scenarios):
            raise field_error("scenario_id", "unknown", "unknown scenario for this simulation")
        if scenario_id is None:
            chosen = next(
                (s for s in run.scenarios if s.action == data.decision_taken and s.feasible),
                None,
            )
            scenario_id = chosen.id if chosen else None
        if best is not None:
            followed = (scenario_id == best.id) if scenario_id else best.action == data.decision_taken
    elif scenario_id is not None:
        raise field_error("scenario_id", "requires_simulation", "a scenario needs its simulation_id")
    has_result = data.actual_recovered_kg is not None or data.actual_revenue_fcfa is not None
    if (
        has_result
        and data.actual_recovered_kg is not None
        and data.actual_recovered_kg > lot.quantity_kg * 1.05
    ):
        raise field_error(
            "actual_recovered_kg",
            "above_lot",
            "recovered quantity cannot exceed the lot",
        )
    outcome = Outcome(
        lot_id=lot.id,
        simulation_run_id=run_id,
        scenario_id=scenario_id,
        decision_taken=data.decision_taken,
        followed_reco=followed,
        actual_recovered_kg=data.actual_recovered_kg,
        actual_revenue_fcfa=data.actual_revenue_fcfa,
        recorded_by=caller.user_id,
    )
    db.add(outcome)
    lot.status = "closed" if has_result else "decided"
    db.flush()
    audit.record(
        db,
        "outcome_recorded",
        "lot",
        lot.id,
        organization_id=caller.organization_id,
        user_id=caller.user_id,
        detail={"decision": data.decision_taken, "with_result": has_result},
    )
    db.commit()
    db.refresh(outcome)
    return outcome


def history(db: Session, caller: Caller, lot_id: uuid.UUID) -> LotHistoryOut:
    lot = get_lot_or_404(db, caller, lot_id)
    analyses = []
    for a in lots_repo.analyses(db, lot.id):
        sims = []
        for run in lots_repo.simulations_for(db, a.id):
            reco = run.recommendation
            best = next(
                (s for s in run.scenarios if reco and s.id == reco.best_scenario_id),
                None,
            )
            sims.append(
                SimulationSummaryOut(
                    id=run.id,
                    created_at=run.created_at,
                    risk_profile=run.risk_profile,
                    n_draws=run.n_draws,
                    seed=run.seed,
                    best_action=best.action if best else None,
                    best_scenario_key=best.key if best else None,
                    confidence=reco.confidence if reco else "none",
                    no_clear_winner=reco.no_clear_winner if reco else True,
                    user_overrides=sum(1 for item in run.assumptions if item.get("user_override")),
                )
            )
        analyses.append(
            AnalysisSummaryOut(
                id=a.id,
                analysis_at=a.analysis_at,
                replay=a.replay,
                risk_level=a.risk_level,
                loss_p10=a.loss_p10,
                loss_p50=a.loss_p50,
                loss_p90=a.loss_p90,
                model_version=a.model_version,
                simulations=sims,
            )
        )
    return LotHistoryOut(lot_id=lot.id, analyses=analyses, outcomes=lots_repo.outcomes(db, lot.id))
