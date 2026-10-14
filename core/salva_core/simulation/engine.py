"""Monte Carlo orchestration for candidate routes and optimized split allocation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import numpy as np

from ..contracts import Lot, Option, Shocks
from ..features import option_durations, route_remaining_h
from ..params import ProductParams
from .allocation import optimize
from .economics import evaluate_portfolio, option_draws, validate_option
from .models import ScenarioResult
from .uncertainty import DEFAULT_DRAWS, MIN_DRAWS, ShockValidationError, draw
from .uncertainty import validate as validate_shocks

RESERVED_SPLIT_ID = "optimized_split"


def _best_probabilities(results: Sequence[ScenarioResult]) -> list[float]:
    eligible = [
        i
        for i, result in enumerate(results)
        if result.feasible and not result.discouraged
    ]
    probabilities = [0.0] * len(results)
    if not eligible:
        return probabilities
    matrices = [np.asarray(results[i].net_draws, dtype=float) for i in eligible]
    if any(x.ndim != 1 or x.size == 0 for x in matrices):
        return probabilities
    if len({x.size for x in matrices}) != 1:
        raise ValueError(
            "feasible results must contain the same number of Monte Carlo draws"
        )
    stacked = np.vstack(matrices)
    best = np.max(stacked, axis=0)
    tied = np.isclose(stacked, best[None, :], rtol=1e-10, atol=1e-8)
    split = tied / np.sum(tied, axis=0, keepdims=True)
    probs = np.mean(split, axis=1)
    for idx, value in zip(eligible, probs, strict=True):
        probabilities[idx] = float(value)
    return probabilities


def run_all(
    model,
    lot: Lot,
    options: Sequence[Option],
    shocks: Shocks,
    params: ProductParams,
    *,
    include_allocation: bool = True,
    store_cap: float | None = None,
) -> list[ScenarioResult]:
    """Evaluate every route and (by default) its best feasible split allocation.

    This five-argument function is the stable adapter surface proposed to P3:
    ``run_all(model, lot, options, shocks, params)``. Candidate actions use the complete
    lot and are marked infeasible when their route/storage capacity cannot carry it.
    Split allocation instead uses each option's capacity and explicitly accounts for
    discarded produce when selling the remainder would have negative expected value.
    """
    if not options:
        raise ValueError("at least one candidate option is required")
    opts = list(options)
    ids = [option.id for option in opts]
    if len(set(ids)) != len(ids):
        raise ValueError("candidate option ids must be unique")
    if RESERVED_SPLIT_ID in ids:
        raise ValueError(f"option id {RESERVED_SPLIT_ID!r} is reserved")
    s = validate_shocks(shocks)
    if s.u.size < MIN_DRAWS:
        raise ShockValidationError(
            f"run_all requires at least {MIN_DRAWS} Monte Carlo draws"
        )
    draws_by_id = {}
    results: list[ScenarioResult] = []
    active_options: list[Option] = []
    for option in opts:
        validate_option(lot, option)
        option_draw = option_draws(model, lot, option, s, params)
        detour_h, hold_h = option_durations(option)
        draws_by_id[option.id] = option_draw
        shelf_life_exceeded = (
            option_draw.remaining_shelf_life_p50_h is not None
            and route_remaining_h(lot, option) + detour_h + hold_h
            > option_draw.remaining_shelf_life_p50_h + 1e-9
        )
        if not shelf_life_exceeded:
            active_options.append(option)
        route_capacity = option.kg
        if option.is_store and option.storage_capacity_kg is not None:
            route_capacity = min(route_capacity, option.storage_capacity_kg)
        if route_capacity + 1e-9 < lot.kg:
            reason = (
                "STORAGE_CAPACITY_BELOW_LOT"
                if option.is_store and route_capacity < option.kg
                else "OPTION_CAPACITY_BELOW_LOT"
            )
            results.append(
                ScenarioResult(
                    id=option.id,
                    action=option.action,
                    feasible=False,
                    loss_p10=None,
                    loss_p50=None,
                    loss_p90=None,
                    recoverable_kg_p10=None,
                    recoverable_kg_p50=None,
                    recoverable_kg_p90=None,
                    gross_value_p10=None,
                    gross_value_p50=None,
                    gross_value_p90=None,
                    net_p10=None,
                    net_p50=None,
                    net_p90=None,
                    infeasible_reason=reason,
                    discouraged=shelf_life_exceeded,
                    discouraged_reason=(
                        "SHELF_LIFE_P50_EXCEEDED" if shelf_life_exceeded else None
                    ),
                    extrapolation_warnings=draws_by_id[
                        option.id
                    ].extrapolation_warnings,
                    temp_mean_c=draws_by_id[option.id].temp_mean_c,
                    temp_max_c=draws_by_id[option.id].temp_max_c,
                    delay_h=float(lot.delay_h),
                    extra_h=detour_h,
                    hold_h=hold_h,
                )
            )
        else:
            result = evaluate_portfolio(
                lot,
                [option],
                {option.id: float(lot.kg)},
                {option.id: draws_by_id[option.id]},
                s,
                params,
                scenario_id=option.id,
                action=option.action,
            )
            if shelf_life_exceeded:
                result = replace(
                    result,
                    discouraged=True,
                    discouraged_reason="SHELF_LIFE_P50_EXCEEDED",
                )
            results.append(result)

    if include_allocation and len(active_options) >= 2:
        mean_values = [
            float(np.mean(draws_by_id[option.id].value_fraction))
            for option in active_options
        ]
        plan = optimize(
            lot.kg, active_options, mean_values, params, store_cap=store_cap
        )
        quantities = {line.option_id: line.kg for line in plan.lines}
        # The optimized alternative is informative when it really splits the lot or
        # explicitly rejects part/all of it. A one-route full-lot optimum duplicates a
        # candidate and would bias probability mass through a mathematically identical row.
        if len(plan.lines) > 1 or plan.discarded_kg > 1e-8:
            results.append(
                evaluate_portfolio(
                    lot,
                    active_options,
                    quantities,
                    draws_by_id,
                    s,
                    params,
                    scenario_id=RESERVED_SPLIT_ID,
                    action="optimized_split",
                    allocation=plan,
                    discarded_kg=plan.discarded_kg,
                )
            )

    # RM materiality is expressed relative to the nominal value of the lot, not
    # relative to whichever net score happens to rank first. Use the highest configured
    # market quote at full lot quantity before loss, surplus discount, or route cost; a
    # caller can override this reference explicitly through Policy.
    lot_reference_value_fcfa = lot.kg * max(
        float(option.market.price) for option in opts
    )
    results = [
        replace(result, lot_reference_value_fcfa=lot_reference_value_fcfa)
        for result in results
    ]
    probabilities = _best_probabilities(results)
    return [
        replace(result, prob_best=prob)
        for result, prob in zip(results, probabilities, strict=True)
    ]


class SimulationEngine:
    """Small stateful facade for the core API; all calculations remain pure Python/NumPy."""

    def __init__(self, model, params: ProductParams) -> None:
        """Bind a loss model and validated product parameters to the facade."""
        self.model = model
        self.params = params

    def run(
        self,
        lot: Lot,
        options: Sequence[Option],
        *,
        n_draws: int = DEFAULT_DRAWS,
        seed: int = 42,
        include_allocation: bool = True,
        store_cap: float | None = None,
    ) -> list[ScenarioResult]:
        """Run a seeded simulation and return route and optional split results."""
        shocks = draw(
            n_draws, seed, market_ids={option.market.id for option in options}
        )
        return run_all(
            self.model,
            lot,
            options,
            shocks,
            self.params,
            include_allocation=include_allocation,
            store_cap=store_cap,
        )
