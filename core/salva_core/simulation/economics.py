"""Pure economic evaluation of candidate routes and allocated portfolios."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

import numpy as np

from ..contracts import LossDistribution, Lot, Option, Shocks
from ..features import assemble, build, option_durations, out_of_range_features
from ..params import ProductParams
from ..risk import classify_risk
from .models import AllocationPlan, ScenarioResult
from .uncertainty import validate as validate_shocks

_TOL = 1e-9
_ACTIONS = frozenset({"continue", "store", "reroute", "sell_local"})


class EconomicsError(ValueError):
    """Raised for invalid economic inputs or a LossModel contract violation."""


@dataclass(frozen=True)
class OptionDraws:
    """Per-draw loss and value fractions for one action, before market economics."""

    loss: np.ndarray
    value_fraction: np.ndarray
    temp_mean_c: float
    temp_max_c: float
    remaining_shelf_life_p50_h: float | None = None
    extrapolation_warnings: tuple[str, ...] = ()


def _finite_nonnegative(value: float, field: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise EconomicsError(f"{field} must be numeric, not bool")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise EconomicsError(f"{field} must be finite and >= 0")
    return number


def validate_option(lot: Lot, option: Option) -> None:
    """Validate the shared contract before any model or economic computation."""
    if not option.id or not isinstance(option.id, str):
        raise EconomicsError("option.id must be a non-empty string")
    if not option.action or not isinstance(option.action, str):
        raise EconomicsError(f"option {option.id}: action must be a non-empty string")
    if option.action not in _ACTIONS:
        raise EconomicsError(
            f"option {option.id}: unsupported action {option.action!r}; "
            f"allowed: {sorted(_ACTIONS)}"
        )
    if _finite_nonnegative(lot.kg, "lot.kg") <= 0:
        raise EconomicsError("lot.kg must be finite and > 0")
    capacity = _finite_nonnegative(option.kg, f"option {option.id}.kg")
    if capacity <= 0:
        raise EconomicsError(f"option {option.id}.kg must be > 0")
    try:
        market_price = float(option.market.price)
        market_absorption = float(option.market.absorb_kg)
    except (TypeError, ValueError, OverflowError) as exc:
        raise EconomicsError(
            f"option {option.id}: market price and absorb_kg must be supplied as numbers"
        ) from exc
    if (
        isinstance(option.market.price, bool)
        or not isfinite(market_price)
        or market_price <= 0
    ):
        raise EconomicsError(f"option {option.id}: market.price must be finite and > 0")
    if (
        isinstance(option.market.absorb_kg, bool)
        or not isfinite(market_absorption)
        or market_absorption < 0
    ):
        raise EconomicsError(
            f"option {option.id}: market.absorb_kg must be finite and >= 0; "
            "resolve missing market defaults in the caller"
        )
    _finite_nonnegative(option.cost, f"option {option.id}.cost")
    _finite_nonnegative(option.extra_h, f"option {option.id}.extra_h")
    if option.hold_h is not None:
        if isinstance(option.hold_h, (bool, np.bool_)):
            raise EconomicsError(
                f"option {option.id}.hold_h must be a duration, not bool"
            )
        hold_h = _finite_nonnegative(option.hold_h, f"option {option.id}.hold_h")
        if hold_h > 0 and not option.is_store:
            raise EconomicsError(f"option {option.id}.hold_h > 0 requires storage")
    storage_rate = _finite_nonnegative(
        option.storage_cost_fcfa_kg_day,
        f"option {option.id}.storage_cost_fcfa_kg_day",
    )
    _finite_nonnegative(
        option.transport_distance_km,
        f"option {option.id}.transport_distance_km",
    )
    _finite_nonnegative(
        option.transport_cost_fcfa_kg_km,
        f"option {option.id}.transport_cost_fcfa_kg_km",
    )
    if storage_rate > 0:
        if not option.is_store:
            raise EconomicsError(
                f"option {option.id}.storage_cost_fcfa_kg_day requires storage"
            )
        if option_durations(option)[1] <= 0:
            raise EconomicsError(
                f"option {option.id}.storage_cost_fcfa_kg_day requires hold_h > 0"
            )
    if option.temp_offset is not None and (
        isinstance(option.temp_offset, (bool, np.bool_))
        or not isfinite(float(option.temp_offset))
    ):
        raise EconomicsError(f"option {option.id}.temp_offset must be finite")
    if option.action == "store" and not option.is_store:
        raise EconomicsError(
            f"option {option.id}: action='store' requires is_store=True"
        )
    if option.is_store and option.action != "store":
        raise EconomicsError(
            f"option {option.id}: is_store=True requires action='store'"
        )
    if option.is_store and option.storage_mode == "none":
        raise EconomicsError(
            f"option {option.id}: a store action needs an explicit storage_mode"
        )
    if option.storage_site_id is not None and not str(option.storage_site_id).strip():
        raise EconomicsError(
            f"option {option.id}.storage_site_id must be non-empty when provided"
        )
    if option.storage_capacity_kg is not None:
        capacity_kg = _finite_nonnegative(
            option.storage_capacity_kg, f"option {option.id}.storage_capacity_kg"
        )
        if capacity_kg <= 0:
            raise EconomicsError(f"option {option.id}.storage_capacity_kg must be > 0")
    unit_cost_fcfa_kg(option)


def unit_cost_fcfa_kg(option: Option) -> float:
    """Return per-physical-kg route, transport and duration-based storage costs."""
    _, hold_h = option_durations(option)
    unit_cost = (
        float(option.cost)
        + float(option.transport_distance_km) * float(option.transport_cost_fcfa_kg_km)
        + float(option.storage_cost_fcfa_kg_day) * hold_h / 24.0
    )
    if not isfinite(unit_cost):
        raise EconomicsError(f"option {option.id}: calculated unit cost must be finite")
    return unit_cost


def option_draws(
    model,
    lot: Lot,
    option: Option,
    shocks: Shocks,
    params: ProductParams,
) -> OptionDraws:
    """Build action features once, then draw its loss through the shared LossModel."""
    n = np.asarray(shocks.u).size
    s = validate_shocks(shocks, n)
    validate_option(lot, option)
    f = build(lot, option, s, params)
    detour_h, hold_h = option_durations(option)
    baseline = assemble(
        params,
        maturity=lot.maturity,
        packaging=lot.packaging,
        age_h=lot.age_h,
        remaining_h=lot.remaining_h,
        temp_air_c=lot.temp_c,
        delay_h=lot.delay_h,
        diurnal_amp_c=lot.diurnal_amp_c,
        extra_h=detour_h,
        hold_h=hold_h,
        temp_offset_c=(
            params.storage_offset(option.storage_mode)
            if option.temp_offset is None
            else option.temp_offset
        ),
        storage_mode=option.storage_mode,
        product=lot.product,
    )
    loss = np.asarray(model.sample_loss(f, s.u), dtype=float)
    try:
        loss = np.broadcast_to(loss, (n,)).astype(float, copy=False)
    except ValueError as exc:
        raise EconomicsError(
            f"LossModel {getattr(model, 'version', 'unknown')} returned shape {loss.shape}; expected ({n},)"
        ) from exc
    if (
        not np.all(np.isfinite(loss))
        or np.any(loss < -_TOL)
        or np.any(loss > 1.0 + _TOL)
    ):
        raise EconomicsError(
            "LossModel.sample_loss must return finite loss fractions in [0, 1]"
        )
    loss = np.clip(loss, 0.0, 1.0)
    shelf_life = None
    estimate_shelf_life = getattr(model, "remaining_shelf_life_p50_h", None)
    if estimate_shelf_life is not None:
        estimate_value = estimate_shelf_life(baseline)
        if estimate_value is not None:
            estimate = np.asarray(estimate_value, dtype=float)
            if estimate.size != 1 or not np.isfinite(estimate).all() or estimate < 0:
                raise EconomicsError(
                    "LossModel.remaining_shelf_life_p50_h must return one finite "
                    "non-negative scalar or None"
                )
            shelf_life = float(estimate.flat[0])
    model_range_check = getattr(model, "extrapolated_features", None)
    extrapolation_warnings = (
        tuple(model_range_check(f))
        if callable(model_range_check)
        else out_of_range_features(f, params)
    )
    return OptionDraws(
        loss=loss,
        value_fraction=1.0 - loss,
        temp_mean_c=float(np.asarray(baseline.temp_mean_c).flat[0]),
        temp_max_c=float(np.asarray(baseline.temp_max_c).flat[0]),
        remaining_shelf_life_p50_h=shelf_life,
        extrapolation_warnings=extrapolation_warnings,
    )


def _quantile(draws: np.ndarray, q: float) -> float:
    return float(np.quantile(draws, q, method="linear"))


def _validated_draws(
    od: OptionDraws, n: int, option_id: str
) -> tuple[np.ndarray, np.ndarray]:
    """Enforce the loss/value invariant even for callers bypassing ``option_draws``."""
    try:
        loss = np.asarray(od.loss, dtype=float)
        value = np.asarray(od.value_fraction, dtype=float)
        temperatures = np.asarray([od.temp_mean_c, od.temp_max_c], dtype=float)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise EconomicsError(
            f"malformed LossModel draws for option {option_id}"
        ) from exc
    if loss.shape != (n,) or value.shape != (n,):
        raise EconomicsError(
            f"LossModel draws for option {option_id} must be vectors of length {n}"
        )
    if not np.all(np.isfinite(loss)) or np.any((loss < 0.0) | (loss > 1.0)):
        raise EconomicsError(
            f"LossModel loss draws for option {option_id} must be finite in [0, 1]"
        )
    if not np.all(np.isfinite(value)) or np.any((value < 0.0) | (value > 1.0)):
        raise EconomicsError(
            f"LossModel value fractions for option {option_id} must be finite in [0, 1]"
        )
    if not np.allclose(value, 1.0 - loss, rtol=0.0, atol=1e-12):
        raise EconomicsError(
            f"LossModel value fractions for option {option_id} must equal 1 - loss"
        )
    if not np.all(np.isfinite(temperatures)):
        raise EconomicsError(
            f"LossModel temperatures for option {option_id} must be finite"
        )
    return loss, value


def evaluate_portfolio(
    lot: Lot,
    options: Sequence[Option],
    quantities_kg: Mapping[str, float],
    draws_by_option: Mapping[str, OptionDraws],
    shocks: Shocks,
    params: ProductParams,
    *,
    scenario_id: str,
    action: str,
    allocation: AllocationPlan | None = None,
    discarded_kg: float = 0.0,
) -> ScenarioResult:
    """Evaluate a fixed physical allocation using aggregate market absorption.

    Recoverable kg means full-price-equivalent kg. Gross revenue applies the market's
    capacity and the configured surplus discount to the aggregate quantity sold there.
    ``Option.cost`` is a linear variable cost in FCFA per physical kg.
    """
    s = validate_shocks(shocks)
    n = s.u.size
    if not 0 <= params.delta <= 1:
        raise EconomicsError("product delta must be in [0, 1]")
    by_id = {o.id: o for o in options}
    if len(by_id) != len(options):
        raise EconomicsError("option ids must be unique")
    if set(quantities_kg) - set(by_id):
        raise EconomicsError("allocation references an unknown option id")
    if not isfinite(float(discarded_kg)) or discarded_kg < -_TOL:
        raise EconomicsError("discarded_kg must be finite and >= 0")

    allocations: dict[str, float] = {}
    total_allocated = 0.0
    for option_id, raw_qty in quantities_kg.items():
        qty = float(raw_qty)
        if not isfinite(qty) or qty < -_TOL:
            raise EconomicsError(f"allocation for {option_id} must be finite and >= 0")
        qty = max(0.0, qty)
        if qty > by_id[option_id].kg + _TOL:
            raise EconomicsError(f"allocation for {option_id} exceeds option capacity")
        allocations[option_id] = qty
        total_allocated += qty
    if abs(total_allocated + max(0.0, discarded_kg) - lot.kg) > 1e-6:
        raise EconomicsError("allocated kg plus discarded kg must equal lot.kg")

    recoverable = np.zeros(n)
    gross = np.zeros(n)
    cost_total = 0.0
    temperature_mean: float | None = None
    temperature_max: float | None = None
    weighted_extra_h = 0.0
    weighted_hold_h = 0.0
    stored_kg = 0.0
    site_capacities: dict[str, float] = {}
    site_usage: dict[str, float] = {}
    market_y: dict[int, np.ndarray] = {}
    market_meta: dict[int, tuple[float, float]] = {}
    market_surplus = np.zeros(n)
    extrapolation_warnings: set[str] = set()

    for option_id, qty in allocations.items():
        if qty <= _TOL:
            continue
        option = by_id[option_id]
        validate_option(lot, option)
        od = draws_by_option.get(option_id)
        if od is None:
            raise EconomicsError(
                f"missing or malformed LossModel draws for option {option_id}"
            )
        _, value_fraction = _validated_draws(od, n, option_id)
        extrapolation_warnings.update(od.extrapolation_warnings)
        y = qty * value_fraction
        recoverable += y
        detour_h, hold_h = option_durations(option)
        cost_total += qty * unit_cost_fcfa_kg(option)
        weighted_extra_h += qty * detour_h
        weighted_hold_h += qty * hold_h
        temperature_mean = (
            od.temp_mean_c
            if temperature_mean is None
            else max(temperature_mean, od.temp_mean_c)
        )
        temperature_max = (
            od.temp_max_c
            if temperature_max is None
            else max(temperature_max, od.temp_max_c)
        )
        if option.is_store:
            stored_kg += qty
            site_id = str(option.storage_site_id or option.id)
            site_capacity = float(option.storage_capacity_kg or option.kg)
            previous_capacity = site_capacities.get(site_id)
            if previous_capacity is not None and not np.isclose(
                previous_capacity, site_capacity
            ):
                raise EconomicsError(
                    f"storage site {site_id} has inconsistent capacities across options"
                )
            site_capacities[site_id] = site_capacity
            site_usage[site_id] = site_usage.get(site_id, 0.0) + qty

        mid = option.market.id
        previous = market_meta.get(mid)
        current = (float(option.market.price), float(option.market.absorb_kg))
        if previous is not None and previous != current:
            raise EconomicsError(
                f"market {mid} has inconsistent price or absorption across options"
            )
        market_meta[mid] = current
        market_y[mid] = market_y.get(mid, np.zeros(n)) + y

    for site_id, used in site_usage.items():
        capacity = site_capacities[site_id]
        if used > capacity + 1e-6:
            raise EconomicsError(
                f"storage site {site_id} capacity exceeded: {used:g} > {capacity:g} kg"
            )

    price_factor = s.price
    absorb_factor = s.absorb
    for market_id, y in market_y.items():
        price, absorb_kg = market_meta[market_id]
        market_capacity_draws = absorb_kg * absorb_factor
        full_price_eq = np.minimum(y, market_capacity_draws)
        surplus_eq = np.maximum(y - market_capacity_draws, 0.0)
        gross += price * price_factor * (full_price_eq + params.delta * surplus_eq)
        market_surplus += surplus_eq

    net = gross - cost_total
    loss = np.clip(1.0 - recoverable / lot.kg, 0.0, 1.0)
    surplus_fraction = np.divide(
        market_surplus,
        recoverable,
        out=np.zeros_like(market_surplus),
        where=recoverable > _TOL,
    )
    n_allocated_options = [by_id[key] for key, qty in allocations.items() if qty > _TOL]
    primary_action = action
    if action != "optimized_split" and len(n_allocated_options) == 1:
        primary_action = n_allocated_options[0].action
    return ScenarioResult(
        id=scenario_id,
        action=primary_action,
        feasible=True,
        loss_p10=_quantile(loss, 0.10),
        loss_p50=_quantile(loss, 0.50),
        loss_p90=_quantile(loss, 0.90),
        recoverable_kg_p10=_quantile(recoverable, 0.10),
        recoverable_kg_p50=_quantile(recoverable, 0.50),
        recoverable_kg_p90=_quantile(recoverable, 0.90),
        gross_value_p10=_quantile(gross, 0.10),
        gross_value_p50=_quantile(gross, 0.50),
        gross_value_p90=_quantile(gross, 0.90),
        net_p10=_quantile(net, 0.10),
        net_p50=_quantile(net, 0.50),
        net_p90=_quantile(net, 0.90),
        risk_level=classify_risk(
            LossDistribution(
                _quantile(loss, 0.10), _quantile(loss, 0.50), _quantile(loss, 0.90)
            ),
            params,
        ).level,
        allocation=allocation,
        net_draws=net,
        loss_draws=loss,
        recoverable_draws=recoverable,
        gross_draws=gross,
        surplus_fraction_p50=_quantile(surplus_fraction, 0.50),
        storage_used_kg=stored_kg,
        storage_capacity_kg=sum(site_capacities.values()),
        temp_mean_c=temperature_mean,
        temp_max_c=temperature_max,
        delay_h=float(lot.delay_h),
        extra_h=weighted_extra_h / total_allocated if total_allocated > _TOL else 0.0,
        hold_h=weighted_hold_h / total_allocated if total_allocated > _TOL else 0.0,
        cost_p50=float(cost_total),
        extrapolation_warnings=tuple(sorted(extrapolation_warnings)),
    )


def evaluate(
    model,
    lot: Lot,
    option: Option,
    shocks: Shocks,
    params: ProductParams,
) -> ScenarioResult:
    """Evaluate one route for the entire lot, or return an explicit capacity infeasibility."""
    validate_option(lot, option)
    s = validate_shocks(shocks)
    od = option_draws(model, lot, option, s, params)
    route_capacity = option.kg
    if option.is_store and option.storage_capacity_kg is not None:
        route_capacity = min(route_capacity, option.storage_capacity_kg)
    if route_capacity + _TOL < lot.kg:
        reason = (
            "STORAGE_CAPACITY_BELOW_LOT"
            if option.is_store and route_capacity < option.kg
            else "OPTION_CAPACITY_BELOW_LOT"
        )
        return ScenarioResult(
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
            discouraged=(
                od.remaining_shelf_life_p50_h is not None
                and lot.remaining_h + sum(option_durations(option))
                > od.remaining_shelf_life_p50_h + 1e-9
            ),
            discouraged_reason=(
                "SHELF_LIFE_P50_EXCEEDED"
                if od.remaining_shelf_life_p50_h is not None
                and lot.remaining_h + sum(option_durations(option))
                > od.remaining_shelf_life_p50_h + 1e-9
                else None
            ),
            extrapolation_warnings=od.extrapolation_warnings,
            temp_mean_c=od.temp_mean_c,
            temp_max_c=od.temp_max_c,
            delay_h=float(lot.delay_h),
            extra_h=option_durations(option)[0],
            hold_h=option_durations(option)[1],
        )
    return evaluate_portfolio(
        lot,
        [option],
        {option.id: float(lot.kg)},
        {option.id: od},
        s,
        params,
        scenario_id=option.id,
        action=option.action,
    )
