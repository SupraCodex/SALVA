"""POST /lots/{id}/analyze: risk + simulation + allocation + recommendation in one call (< 3 s).

Orchestration only: reads the lot, enriches it, calls the engine (salva_core, owned by R5), stores the result.
No scientific logic here."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Analysis, Lot, ScenarioRow
from app.deps import Caller
from app.errors import ApiError, field_error, not_found
from app.repositories import analyses as analyses_repo
from app.repositories import reference as ref_repo
from app.schemas.analysis import AnalysisOut, AnalyzeIn
from app.services import engines, enrichment
from app.services.common import hours_between, utcnow
from app.services.lot_service import get_or_404 as get_lot_or_404
from app.services.options import options_for


def to_core_lot(lot: Lot, temp_c: float, now):
    from salva_core.contracts import Lot as CoreLot
    return CoreLot(kg=lot.kg, maturity=lot.maturity, packaging=lot.packaging,
                   age_h=max(0.0, hours_between(now, lot.harvested_at)),
                   remaining_h=max(0.0, hours_between(lot.eta_current, now)), temp_c=temp_c,
                   delay_h=hours_between(lot.eta_current, lot.eta_planned))


def analyze(db: Session, caller: Caller, lot_id: int, body: AnalyzeIn) -> Analysis:
    s = get_settings()
    lot = get_lot_or_404(db, caller, lot_id)
    if lot.status == "closed":
        raise ApiError(409, "lot-closed", "This lot is closed.")
    now = body.now or utcnow()
    if now < lot.harvested_at:
        raise field_error("now", "before_harvest", "analysis time must be after harvest")
    model = engines.loss_model(lot.product)       # 503 if the engine (core/) is not installed
    p = engines.products()[lot.product]
    from salva_core.features import build
    from salva_core.loss_model.factors import top_factors
    from salva_core.loss_model.sampling import quantiles
    from salva_core.recommendation import policy_for, recommend
    from salva_core.simulation import draw, run_all

    temp = enrichment.temperature(lot, now)
    price = enrichment.price(lot)
    clot = to_core_lot(lot, temp.value, now)
    n, seed = body.n_draws or s.n_draws, s.seed if body.seed is None else body.seed
    S = draw(n, seed)

    # ---- risk: loss distribution if nothing changes
    loss = model.sample_loss(build(clot, None, S, p), S.u)
    q = quantiles(loss)
    factors = top_factors(model, clot, p)

    # ---- decisions
    absorb = body.absorb_override or {}
    scenarios, assumptions = options_for(db, clot, lot, p, price.value, absorb)
    results = run_all(model, clot, scenarios, S, p)
    reco = recommend(results, policy_for(body.risk_profile), clot)

    mk = {m.id: m for m in ref_repo.markets(db)}
    assumptions = [
        {"name": "temperature_c", "value": temp.value, "source": temp.source},
        {"name": f"price_fcfa_kg:{lot.destination.name}", "value": price.value, "source": price.source},
        *[{"name": f"absorb_kg_day:{mk[i].name}", "value": absorb.get(i, mk[i].absorb_kg_day),
           "source": "user override" if i in absorb else f"markets.csv ({mk[i].source})"}
          for i in sorted({o.market.id for sc in scenarios for o in sc.legs})],
        {"name": "surplus_price_fraction", "value": p.delta, "source": "products.yaml"},
        {"name": "product_parameters", "value": p.code, "source": p.source_note},
        *assumptions,
    ]
    inputs = {"age_h": clot.age_h, "remaining_h": clot.remaining_h, "delay_h": clot.delay_h,
              "temp_c": temp.value, "temp_source": temp.source, "price_fcfa_kg": price.value,
              "price_source": price.source, "replay": body.now is not None}
    a = Analysis(lot_id=lot.id, model_version=model.version, model_fallback=getattr(model, "is_fallback", False),
                 analyzed_at=now, seed=seed, n_draws=n, inputs=inputs, assumptions=assumptions,
                 loss_p10=q["p10"], loss_p50=q["p50"], loss_p90=q["p90"], risk_level=model.risk_level(q["p50"]),
                 factors=factors)
    rows = [ScenarioRow(position=i, key=r.id, action=r.scenario.action, allocation=r.allocation,
                        feasible=r.feasible, infeasible_reason=r.scenario.infeasible_reason,
                        kg_equiv=r.kg_equiv, net_value_fcfa=r.net_value, prob_best=r.prob_best)
            for i, r in enumerate(results)]
    return analyses_repo.save(db, a, rows, {
        "scenario_key": reco.scenario_id, "tied_keys": reco.tied, "confidence": reco.confidence,
        "rationale": reco.rationale, "ranking": reco.ranking,
        "policy": {"risk_profile": body.risk_profile, "lam": policy_for(body.risk_profile).lam,
                   "materiality": policy_for(body.risk_profile).materiality}})


def get_or_404(db: Session, caller: Caller, analysis_id: int) -> Analysis:
    a = analyses_repo.get(db, caller.organization_id, analysis_id)
    if a is None:
        raise not_found("Analysis")
    return a


def to_out(a: Analysis) -> AnalysisOut:
    reco = a.recommendation
    by_id = {s.id: s for s in a.scenarios}
    return AnalysisOut(
        id=a.id, lot_id=a.lot_id, analyzed_at=a.analyzed_at,
        model={"version": a.model_version, "fallback": a.model_fallback}, seed=a.seed, n_draws=a.n_draws,
        risk={"level": a.risk_level, "loss": {"p10": a.loss_p10, "p50": a.loss_p50, "p90": a.loss_p90},
              "factors": a.factors},
        scenarios=[{"id": s.id, "key": s.key, "action": s.action, "feasible": s.feasible,
                    "infeasible_reason": s.infeasible_reason, "allocation": s.allocation, "kg_equiv": s.kg_equiv,
                    "net_value_fcfa": s.net_value_fcfa, "prob_best": s.prob_best} for s in a.scenarios],
        recommendation=None if reco is None else {
            "scenario_id": reco.scenario_id,
            "action": by_id[reco.scenario_id].action if reco.scenario_id in by_id else None,
            "confidence": reco.confidence, "tied_scenario_ids": reco.tied, "rationale": reco.rationale,
            "risk_profile": reco.policy.get("risk_profile", "balanced")},
        assumptions=a.assumptions,
    )
