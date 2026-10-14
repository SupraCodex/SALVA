"""Decision simulation (FR-07 to FR-10, FR-17, FR-19).

The backend decides which actions physically exist for a lot (FR-07); ``salva_core`` then
simulates them by Monte Carlo with common random numbers, optimizes the split allocation
and ranks them. Every value used is returned as an assumption with its source.

Position assumption: the live position of the truck is unknown, so detours and alternative
markets are computed from the departure place. This is shown to the user.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, replace

from salva_core.contracts import Market as CoreMarket
from salva_core.contracts import Option
from salva_core.recommendation import Policy, recommend
from salva_core.simulation import analyze_sensitivity, draw, run_all
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Analysis,
    Lot,
    Market,
    Recommendation,
    Scenario,
    SimulationRun,
    StorageSite,
)
from app.deps import Caller
from app.errors import ApiError, not_found
from app.repositories import lots as lots_repo
from app.repositories import reference as ref_repo
from app.schemas.analysis import (
    RecommendationOut,
    ScenarioOut,
    SensitivityIn,
    SensitivityOut,
    SimulationCreate,
    SimulationOut,
)
from app.schemas.common import build
from app.services import engine, enrichment
from app.services.analysis import core_lot

RISK_PROFILES = {"prudent": 0.8, "balanced": 0.5, "ambitious": 0.2}
ACTION_LABELS = {
    "continue": ("Continuer vers {market}", "Continue to {market}"),
    "sell_local": ("Vendre sur place à {market}", "Sell locally at {market}"),
    "reroute": ("Réorienter vers {market}", "Reroute to {market}"),
    "store": ("Stocker à {site}, puis {market}", "Store at {site}, then {market}"),
    "optimized_split": ("Répartition optimisée", "Optimized split"),
}
UNAVAILABLE_LABELS = {
    "sell_local": {"fr": "Vendre sur place", "en": "Sell locally"},
    "reroute": {"fr": "Réorienter", "en": "Reroute"},
    "store": {"fr": "Stocker", "en": "Store"},
}


@dataclass(frozen=True)
class RouteMeta:
    key: str
    action: str
    market: Market
    site: StorageSite | None
    km: float
    hours: float
    transit_saving_h: float
    extra_h: float
    distance_source: str

    def label(self) -> dict[str, str]:
        fr, en = ACTION_LABELS[self.action]
        site = self.site.name if self.site else ""
        name = f"{self.market.name} ({self.market.city})"
        return {
            "fr": fr.format(market=name, site=site),
            "en": en.format(market=name, site=site),
        }


@dataclass
class Plan:
    options: list[Option]
    meta: dict[str, RouteMeta]
    unavailable: list[tuple[str, str]]  # (action, reason code)
    assumptions: list[dict]
    market_index: dict[uuid.UUID, int]


def _assumption(key, value, unit, source, override=False) -> dict:
    return {
        "key": key,
        "value": value,
        "unit": unit,
        "source": source,
        "user_override": override,
    }


def build_plan(db: Session, lot: Lot, analysis: Analysis, body: SimulationCreate) -> Plan:
    settings = get_settings()
    over = body.assumptions
    clot = core_lot(lot, analysis)
    markets = ref_repo.markets(db)
    market_index = {m.id: i + 1 for i, m in enumerate(sorted(markets, key=lambda m: m.code))}
    known = set(market_index)
    unknown = [str(mid) for mid in over.markets if mid not in known]
    if unknown:
        raise ApiError(
            422,
            "validation-error",
            "One or more fields are invalid.",
            [
                {
                    "field": "assumptions.markets",
                    "code": "unknown",
                    "message": "unknown market id",
                }
            ],
        )
    hold_h = over.hold_h if over.hold_h is not None else settings.hold_h
    per_km = (
        over.transport_fcfa_kg_km if over.transport_fcfa_kg_km is not None else settings.transport_fcfa_kg_km
    )

    def core_market(m: Market) -> CoreMarket:
        o = over.markets.get(m.id)
        if o and o.price_fcfa_kg is not None:
            price = float(o.price_fcfa_kg)
        elif m.id == lot.destination_market_id and lot.price_override_fcfa_kg is not None:
            price = float(lot.price_override_fcfa_kg)
        else:
            price = float(m.ref_price_fcfa_kg)
        absorb = float(o.absorption_kg) if o and o.absorption_kg is not None else float(m.absorption_kg_day)
        return CoreMarket(market_index[m.id], m.name, price, absorb)

    origin = lot.origin
    dest = lot.destination
    leg_dest = enrichment.route(origin, dest)
    options: list[Option] = []
    meta: dict[str, RouteMeta] = {}
    unavailable: list[tuple[str, str]] = []
    used_markets: set[uuid.UUID] = {dest.id}

    key = f"continue:{dest.code}"
    options.append(Option(key, "continue", clot.kg, core_market(dest)))
    meta[key] = RouteMeta(
        key,
        "continue",
        dest,
        None,
        leg_dest.km,
        leg_dest.hours,
        0.0,
        0.0,
        leg_dest.source,
    )

    legs = {m.id: enrichment.route(origin, m) for m in markets if m.id != dest.id}

    # Sell locally: nearest market to the departure place within the radius, closer than the destination.
    local = sorted(
        (
            m
            for m in markets
            if m.id != dest.id
            and legs[m.id].km <= settings.sell_local_radius_km
            and legs[m.id].km < leg_dest.km
        ),
        key=lambda m: (legs[m.id].km, m.code),
    )
    if local:
        m = local[0]
        leg = legs[m.id]
        saving = max(0.0, leg_dest.hours - leg.hours)
        extra = max(0.0, leg.hours - leg_dest.hours)
        key = f"sell_local:{m.code}"
        options.append(
            Option(
                key,
                "sell_local",
                clot.kg,
                core_market(m),
                extra_h=extra,
                transit_saving_h=saving,
            )
        )
        meta[key] = RouteMeta(key, "sell_local", m, None, leg.km, leg.hours, saving, extra, leg.source)
        used_markets.add(m.id)
    else:
        unavailable.append(("sell_local", "NO_LOCAL_MARKET"))

    # Reroute to other markets, nearest first.
    others = sorted(
        (m for m in markets if m.id not in used_markets),
        key=lambda m: (legs[m.id].km, m.code),
    )
    for m in others[: settings.max_reroute_options]:
        leg = legs[m.id]
        shift = leg.hours - leg_dest.hours
        extra_km = max(0.0, leg.km - leg_dest.km)
        key = f"reroute:{m.code}"
        options.append(
            Option(
                key,
                "reroute",
                clot.kg,
                core_market(m),
                extra_h=max(0.0, shift),
                transit_saving_h=max(0.0, -shift),
                transport_distance_km=extra_km,
                transport_cost_fcfa_kg_km=per_km,
            )
        )
        meta[key] = RouteMeta(
            key,
            "reroute",
            m,
            None,
            leg.km,
            leg.hours,
            max(0.0, -shift),
            max(0.0, shift),
            leg.source,
        )
    if not others:
        unavailable.append(("reroute", "NO_ALTERNATIVE_MARKET"))

    # Store at the organization's active sites (least detour first), then sell at the destination.
    sites = ref_repo.storage_sites(db, lot.organization_id, active_only=True)
    scored = []
    for site in sites:
        to_site = enrichment.routing.leg(
            origin.code,
            origin.lat,
            origin.lon,
            site.location.code,
            site.location.lat,
            site.location.lon,
        )
        to_dest = enrichment.routing.leg(
            site.location.code,
            site.location.lat,
            site.location.lon,
            dest.location.code,
            dest.location.lat,
            dest.location.lon,
        )
        detour_km = max(0.0, to_site.km + to_dest.km - leg_dest.km)
        detour_h = max(0.0, to_site.hours + to_dest.hours - leg_dest.hours)
        scored.append((detour_km, site, detour_h, to_site.source))
    scored.sort(key=lambda t: (t[0], t[1].name))
    p = engine.params(lot.product_code)
    for detour_km, site, detour_h, source in scored[: settings.max_storage_options]:
        key = f"store:{site.id.hex[:8]}"
        options.append(
            Option(
                key,
                "store",
                clot.kg,
                core_market(dest),
                extra_h=detour_h,
                is_store=True,
                storage_mode=site.temp_mode,
                temp_offset=p.storage_offset(site.temp_mode),
                storage_site_id=str(site.id),
                storage_capacity_kg=float(site.capacity_kg),
                hold_h=float(hold_h),
                storage_cost_fcfa_kg_day=float(site.cost_fcfa_kg_day),
                transport_distance_km=detour_km,
                transport_cost_fcfa_kg_km=per_km,
            )
        )
        meta[key] = RouteMeta(key, "store", dest, site, detour_km, detour_h, 0.0, detour_h, source)
    if not scored:
        unavailable.append(("store", "NO_STORAGE_SITE"))

    # Assumptions shown to the user (DAT-01): value, unit, source, and whether the user changed it.
    src_temp = analysis.feature_sources.get("temp_air_c", "")
    assumptions = [
        _assumption("temperature_air_c", analysis.features["temp_air_c"], "°C", src_temp),
        _assumption(
            "remaining_transit_h",
            analysis.features["remaining_transit_h"],
            "h",
            "ETA entered by the user",
        ),
        _assumption(
            "hold_h",
            hold_h,
            "h",
            "user" if over.hold_h is not None else "default",
            over.hold_h is not None,
        ),
        _assumption(
            "transport_fcfa_kg_km",
            per_km,
            "FCFA/kg/km",
            "user" if over.transport_fcfa_kg_km is not None else "default assumption",
            over.transport_fcfa_kg_km is not None,
        ),
        _assumption(
            "surplus_price_fraction",
            over.surplus_price_fraction if over.surplus_price_fraction is not None else p.delta,
            "fraction",
            "user" if over.surplus_price_fraction is not None else "products.yaml (assumption)",
            over.surplus_price_fraction is not None,
        ),
        _assumption("position", "departure place", "", "assumption: live truck position unknown"),
    ]
    involved = {meta_item.market.id: meta_item.market for meta_item in meta.values()}
    for m in sorted(involved.values(), key=lambda m: m.code):
        o = over.markets.get(m.id)
        cm = core_market(m)
        price_src = (
            "manual (lot)"
            if m.id == dest.id
            and lot.price_override_fcfa_kg is not None
            and not (o and o.price_fcfa_kg is not None)
            else "user"
            if o and o.price_fcfa_kg is not None
            else f"reference: {m.assumption_note}"
        )
        assumptions.append(
            _assumption(
                f"price_fcfa_kg:{m.code}",
                cm.price,
                "FCFA/kg",
                price_src,
                bool(o and o.price_fcfa_kg is not None),
            )
        )
        assumptions.append(
            _assumption(
                f"absorption_kg:{m.code}",
                cm.absorb_kg,
                "kg",
                "user" if o and o.absorption_kg is not None else f"reference: {m.assumption_note}",
                bool(o and o.absorption_kg is not None),
            )
        )
    for key, item in meta.items():
        if item.action != "continue":
            assumptions.append(_assumption(f"route_km:{key}", item.km, "km", item.distance_source))
    assumptions.append(_assumption(f"route_km:continue:{dest.code}", leg_dest.km, "km", leg_dest.source))
    for site in {m.site.id: m.site for m in meta.values() if m.site}.values():
        assumptions.append(
            _assumption(
                f"storage_capacity_kg:{site.name}",
                site.capacity_kg,
                "kg",
                "organization storage site",
            )
        )
        assumptions.append(
            _assumption(
                f"storage_cost_fcfa_kg_day:{site.name}",
                site.cost_fcfa_kg_day,
                "FCFA/kg/day",
                "organization storage site",
            )
        )
    return Plan(options, meta, unavailable, assumptions, market_index)


def _params_for(lot: Lot, body: SimulationCreate):
    p = engine.params(lot.product_code)
    if body.assumptions.surplus_price_fraction is not None:
        p = replace(p, delta=float(body.assumptions.surplus_price_fraction))
    return p


def _q(values: dict | None) -> dict:
    values = values or {}
    return {
        "p10": values.get("p10"),
        "p50": values.get("p50"),
        "p90": values.get("p90"),
    }


def simulate(db: Session, caller: Caller, analysis_id: uuid.UUID, body: SimulationCreate) -> SimulationRun:
    settings = get_settings()
    analysis = lots_repo.analysis(db, caller.organization_id, analysis_id)
    if analysis is None:
        raise not_found("Analysis")
    lot = analysis.lot
    if lot.status == "closed":
        raise ApiError(409, "lot-closed", "This lot is closed.")
    n_draws = body.n_draws or settings.n_draws
    seed = settings.seed if body.seed is None else body.seed
    started = time.perf_counter()
    plan = build_plan(db, lot, analysis, body)
    p = _params_for(lot, body)
    model = engine.loss_model(lot.product_code)
    clot = core_lot(lot, analysis)
    policy = Policy(lam=RISK_PROFILES[body.risk_profile])
    shocks = draw(n_draws, seed, market_ids=sorted({o.market.id for o in plan.options}))
    try:
        results = run_all(model, clot, plan.options, shocks, p)
        reco = recommend(results, policy)
    except ValueError as exc:  # core contract violation: never hide it behind a partial result
        raise ApiError(422, "simulation-invalid", f"The simulation could not run: {exc}") from exc
    duration_ms = round((time.perf_counter() - started) * 1000, 1)

    run = SimulationRun(
        id=uuid.uuid4(),
        analysis_id=analysis.id,
        n_draws=n_draws,
        seed=seed,
        risk_profile=body.risk_profile,
        assumptions=plan.assumptions,
        request=body.model_dump(mode="json"),
        duration_ms=duration_ms,
    )
    db.add(run)
    rows: dict[str, Scenario] = {}
    for position, r in enumerate(results):
        data = r.as_dict()
        allocation_plan = data.pop("allocation", None)
        meta = plan.meta.get(r.id)
        if allocation_plan:
            lines = [
                {
                    "scenario_key": line["option_id"],
                    "action": plan.meta[line["option_id"]].action,
                    "label": plan.meta[line["option_id"]].label(),
                    "kg": round(line["kg"], 3),
                    "full_price_kg": round(line["full_price_kg"], 3),
                    "surplus_kg": round(line["surplus_kg"], 3),
                }
                for line in allocation_plan["lines"]
                if line["kg"] > 1e-6
            ]
            data["discarded_kg"] = allocation_plan["discarded_kg"]
            label = dict(zip(("fr", "en"), ACTION_LABELS["optimized_split"], strict=True))
        else:
            lines = (
                [
                    {
                        "scenario_key": r.id,
                        "action": r.action,
                        "label": meta.label(),
                        "kg": float(lot.quantity_kg),
                        "full_price_kg": float(lot.quantity_kg),
                        "surplus_kg": 0.0,
                    }
                ]
                if r.feasible and meta
                else []
            )
            data["discarded_kg"] = 0.0
            label = meta.label() if meta else {"fr": r.id, "en": r.id}
        if meta:
            data["transit_saving_h"] = meta.transit_saving_h
            data["route_km"] = meta.km
        row = Scenario(
            id=uuid.uuid4(),
            simulation_run_id=run.id,
            position=position,
            key=r.id,
            action=r.action,
            market_id=meta.market.id if meta else None,
            storage_site_id=meta.site.id if meta and meta.site else None,
            label=label,
            allocation=lines,
            feasible=r.feasible,
            infeasible_reason=r.infeasible_reason,
            discouraged=r.discouraged,
            discouraged_reason=r.discouraged_reason,
            results=data,
            prob_best=float(r.prob_best),
        )
        rows[r.id] = row
        db.add(row)
    for offset, (action, reason) in enumerate(plan.unavailable):
        db.add(
            Scenario(
                id=uuid.uuid4(),
                simulation_run_id=run.id,
                position=len(results) + offset,
                key=f"{action}:unavailable",
                action=action,
                label=UNAVAILABLE_LABELS[action],
                allocation=[],
                feasible=False,
                infeasible_reason=reason,
                results={},
                prob_best=0.0,
            )
        )
    best = rows.get(reco.best_id) if reco.best_id else None
    db.flush()
    db.add(
        Recommendation(
            id=uuid.uuid4(),
            simulation_run_id=run.id,
            best_scenario_id=best.id if best else None,
            confidence=reco.confidence,
            no_clear_winner=reco.no_clear_winner,
            rationale_codes=list(reco.rationale_codes),
            ranked_keys=list(reco.ranked_ids),
            scores_fcfa={k: float(v) for k, v in reco.scores_fcfa},
            prob_best=float(reco.prob_best),
            gap_fraction=None if reco.gap_fraction is None else float(reco.gap_fraction),
            policy={
                "risk_profile": body.risk_profile,
                "lam": policy.lam,
                "materiality": policy.materiality,
            },
            assumption_codes=list(reco.assumptions),
        )
    )
    db.commit()
    db.expire_all()
    stored = lots_repo.simulation(db, caller.organization_id, run.id)
    if stored is None:  # pragma: no cover - the row was committed just above
        raise ApiError(503, "storage-error", "The simulation could not be read back.")
    return stored


def get_or_404(db: Session, caller: Caller, simulation_id: uuid.UUID) -> SimulationRun:
    run = lots_repo.simulation(db, caller.organization_id, simulation_id)
    if run is None:
        raise not_found("Simulation")
    return run


def scenario_out(s: Scenario) -> ScenarioOut:
    r = s.results or {}
    return build(
        ScenarioOut,
        id=s.id,
        key=s.key,
        action=s.action,
        label=s.label,
        market_id=s.market_id,
        storage_site_id=s.storage_site_id,
        feasible=s.feasible,
        infeasible_reason=s.infeasible_reason,
        discouraged=s.discouraged,
        discouraged_reason=s.discouraged_reason,
        loss=_q(r.get("loss")),
        recoverable_kg=_q(r.get("recoverable_kg")),
        gross_value_fcfa=_q(r.get("gross_value_fcfa")),
        net_value_fcfa=_q(r.get("net_value_fcfa")),
        prob_best=s.prob_best,
        risk_level=r.get("risk_level"),
        allocation=s.allocation,
        discarded_kg=float(r.get("discarded_kg", 0.0) or 0.0),
        storage_used_kg=float(r.get("storage_used_kg", 0.0) or 0.0),
        extra_h=float(r.get("extra_h", 0.0) or 0.0),
        hold_h=float(r.get("hold_h", 0.0) or 0.0),
        transit_saving_h=float(r.get("transit_saving_h", 0.0) or 0.0),
        cost_p50_fcfa=float(r.get("cost_p50_fcfa", 0.0) or 0.0),
        extrapolation_warnings=list(r.get("extrapolation_warnings", []) or []),
    )


def recommendation_out(run: SimulationRun) -> RecommendationOut:
    reco = run.recommendation
    if reco is None:
        raise not_found("Recommendation")
    by_key = {s.key: s for s in run.scenarios}
    best = next((s for s in run.scenarios if s.id == reco.best_scenario_id), None)
    ranked = [by_key[k].id for k in reco.ranked_keys if k in by_key]
    candidates = ranked[:2] if reco.no_clear_winner else ([best.id] if best else [])
    return build(
        RecommendationOut,
        id=reco.id,
        simulation_id=run.id,
        best_scenario_id=best.id if best else None,
        best_scenario_key=best.key if best else None,
        best_action=best.action if best else None,
        confidence=reco.confidence,
        no_clear_winner=reco.no_clear_winner,
        prob_best=reco.prob_best,
        gap_fraction=reco.gap_fraction,
        rationale_codes=reco.rationale_codes,
        ranked_scenario_ids=ranked,
        candidate_scenario_ids=candidates,
        low_risk=run.analysis.risk_level == "low",
        policy=reco.policy,
        assumption_codes=reco.assumption_codes,
    )


def to_out(run: SimulationRun) -> SimulationOut:
    return build(
        SimulationOut,
        id=run.id,
        analysis_id=run.analysis_id,
        lot_id=run.analysis.lot_id,
        n_draws=run.n_draws,
        seed=run.seed,
        risk_profile=run.risk_profile,
        duration_ms=run.duration_ms,
        assumptions=run.assumptions,
        scenarios=[scenario_out(s) for s in run.scenarios],
        recommendation=recommendation_out(run),
        created_at=run.created_at,
    )


def _grid(center: float, steps: tuple[float, ...], lo: float, hi: float) -> list[float]:
    values = sorted({round(min(hi, max(lo, center + s)), 1) for s in steps})
    return values


def sensitivity(db: Session, caller: Caller, simulation_id: uuid.UUID, body: SensitivityIn) -> SensitivityOut:
    run = get_or_404(db, caller, simulation_id)
    analysis = run.analysis
    lot = analysis.lot
    request = SimulationCreate.model_validate(run.request)
    plan = build_plan(db, lot, analysis, request)
    p = _params_for(lot, request)
    model = engine.loss_model(lot.product_code)
    clot = core_lot(lot, analysis)
    temps = body.temperatures_c or _grid(clot.temp_c, (-6, -3, 0, 3, 6), 5.0, 45.0)
    delays = body.delays_h or sorted({0.0, round(clot.delay_h, 1), 6.0, 12.0, 24.0, 36.0})[:7]
    if any(t < 0 or t > 50 for t in temps) or any(d < 0 or d > 72 for d in delays):
        raise ApiError(
            422,
            "validation-error",
            "One or more fields are invalid.",
            [
                {
                    "field": "grid",
                    "code": "out_of_range",
                    "message": "temperature 0-50 °C, delay 0-72 h",
                }
            ],
        )
    n = max(1000, min(run.n_draws, 2000))
    try:
        result = analyze_sensitivity(
            model,
            clot,
            plan.options,
            p,
            temps,
            delays,
            n_draws=n,
            seed=run.seed,
            policy=Policy(lam=RISK_PROFILES[run.risk_profile]),
        )
    except ValueError as exc:
        raise ApiError(422, "sensitivity-invalid", f"The sensitivity analysis could not run: {exc}") from exc
    action = {k: m.action for k, m in plan.meta.items()} | {"optimized_split": "optimized_split"}
    points = [
        {
            "temp_c": pt.temp_c,
            "delay_h": pt.delay_h,
            "best_scenario_key": pt.best_id,
            "best_action": action.get(pt.best_id) if pt.best_id else None,
            "confidence": pt.confidence,
        }
        for pt in result.points
    ]
    transitions = []
    for t in result.transitions:
        if t.from_temp_c == t.to_temp_c:
            axis, a, b, fixed = "delay", t.from_delay_h, t.to_delay_h, t.from_temp_c
        else:
            axis, a, b, fixed = (
                "temperature",
                t.from_temp_c,
                t.to_temp_c,
                t.from_delay_h,
            )
        transitions.append(
            {
                "axis": axis,
                "from_value": a,
                "to_value": b,
                "fixed_value": fixed,
                "from_action": action.get(t.from_best_id) if t.from_best_id else None,
                "to_action": action.get(t.to_best_id) if t.to_best_id else None,
            }
        )
    return build(
        SensitivityOut,
        simulation_id=run.id,
        n_draws=n,
        seed=run.seed,
        current={"temp_c": clot.temp_c, "delay_h": clot.delay_h},
        temperatures_c=list(result.temperatures_c),
        delays_h=list(result.delays_h),
        points=points,
        transitions=transitions,
    )
