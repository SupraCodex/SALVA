from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import Caller, get_caller, limit_compute, limit_explain
from app.llm.schemas import Lang
from app.schemas.analysis import (
    AnalysisOut,
    RecommendationOut,
    SensitivityIn,
    SensitivityOut,
    SimulationCreate,
    SimulationOut,
)
from app.schemas.outcome import ExplanationIn, ExplanationOut
from app.services import analysis as analysis_service
from app.services import explanation as explanation_service
from app.services import simulation as simulation_service

router = APIRouter(tags=["analysis and decisions"])


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisOut,
    summary="Read a stored analysis",
)
def get_analysis(
    analysis_id: uuid.UUID,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    return analysis_service.to_out(analysis_service.get_or_404(db, caller, analysis_id))


@router.post(
    "/analyses/{analysis_id}/simulations",
    response_model=SimulationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Simulate the feasible decisions (Monte Carlo + optimized split) and recommend",
)
def create_simulation(
    analysis_id: uuid.UUID,
    body: SimulationCreate | None = None,
    caller: Caller = Depends(limit_compute),
    db: Session = Depends(get_db),
):
    run = simulation_service.simulate(db, caller, analysis_id, body or SimulationCreate())
    return simulation_service.to_out(run)


@router.get(
    "/simulations/{simulation_id}",
    response_model=SimulationOut,
    summary="Scenarios, results and recommendation of a simulation",
)
def get_simulation(
    simulation_id: uuid.UUID,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    return simulation_service.to_out(simulation_service.get_or_404(db, caller, simulation_id))


@router.get(
    "/simulations/{simulation_id}/recommendation",
    response_model=RecommendationOut,
    summary="Recommendation of a simulation",
)
def get_recommendation(
    simulation_id: uuid.UUID,
    caller: Caller = Depends(get_caller),
    db: Session = Depends(get_db),
):
    return simulation_service.recommendation_out(simulation_service.get_or_404(db, caller, simulation_id))


@router.post(
    "/simulations/{simulation_id}/sensitivity",
    response_model=SensitivityOut,
    summary="Temperature x delay grid: where the recommended action changes",
)
def sensitivity(
    simulation_id: uuid.UUID,
    body: SensitivityIn | None = None,
    caller: Caller = Depends(limit_compute),
    db: Session = Depends(get_db),
):
    return simulation_service.sensitivity(db, caller, simulation_id, body or SensitivityIn())


@router.post(
    "/recommendations/{reco_id}/explanations",
    response_model=ExplanationOut,
    summary="Plain-language explanation: validated LLM, otherwise the template (always 200)",
)
async def explain(
    reco_id: uuid.UUID,
    body: ExplanationIn | None = None,
    caller: Caller = Depends(limit_explain),
    db: Session = Depends(get_db),
):
    lang: Lang = body.lang if body and body.lang else ("en" if caller.locale == "en" else "fr")
    return explanation_service.to_out(await explanation_service.explain(db, caller, reco_id, lang))
