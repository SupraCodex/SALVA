"""Linear-programming allocation across routes, storage sites and market tiers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from math import isfinite
from numbers import Real

import numpy as np
from scipy.optimize import linprog

from ..contracts import Option
from ..features import option_durations
from ..params import ProductParams
from .economics import EconomicsError, validate_option
from .models import AllocationLine, AllocationPlan

_TOL = 1e-8


class AllocationError(ValueError):
    """Raised when the linear allocation problem is malformed or cannot be solved."""


def optimize(
    lot_kg: float,
    options: Sequence[Option],
    value_fractions: Sequence[float] | np.ndarray,
    params: ProductParams,
    store_cap: float | None = None,
) -> AllocationPlan:
    """Maximize expected net value at P50 while respecting physical and market limits.

    ``value_fractions[i]`` is the Monte Carlo mean fraction of value retained on option ``i``.
    For each option the LP chooses physical kg sold in the full-price tier and in the
    discounted-surplus tier. Full-price-equivalent kg across all routes to the same market
    share one absorption constraint. Storage options sharing ``storage_site_id`` share one
    site capacity; without that id an option is treated as its own site.

    An explicit discard variable guarantees mass conservation even when every sale route
    has negative net value. In the returned plan, discarded kg are visible rather than
    silently omitted. ``store_cap``, when supplied, is an additional overall store limit.
    """
    if not isfinite(float(lot_kg)) or lot_kg <= 0:
        raise AllocationError("lot_kg must be finite and > 0")
    if not options:
        raise AllocationError("at least one allocation option is required")
    opts = list(options)
    ids = [o.id for o in opts]
    if len(set(ids)) != len(ids):
        raise AllocationError("option ids must be unique")
    if "optimized_split" in ids:
        raise AllocationError(
            "option id 'optimized_split' is reserved by the simulation engine"
        )
    for opt in opts:
        try:
            validate_option(_lot_stub(float(lot_kg)), opt)
        except (EconomicsError, AttributeError, TypeError, ValueError) as exc:
            raise AllocationError(str(exc)) from exc

    values = np.asarray(value_fractions, dtype=float)
    if values.shape != (len(opts),) or not np.all(np.isfinite(values)):
        raise AllocationError(
            f"value_fractions must be a finite vector of length {len(opts)}"
        )
    if np.any((values < 0.0) | (values > 1.0)):
        raise AllocationError("value_fractions must be in [0, 1]")
    if not isfinite(float(params.delta)) or not 0.0 <= params.delta <= 1.0:
        raise AllocationError("product delta must be in [0, 1]")
    if store_cap is not None and (
        isinstance(store_cap, bool)
        or not isinstance(store_cap, Real)
        or not isfinite(float(store_cap))
        or store_cap < 0
    ):
        raise AllocationError("store_cap must be finite and >= 0 when provided")

    n = len(opts)
    # Variables: n full-price physical quantities, n surplus quantities, one discard.
    n_vars = 2 * n + 1
    objective = np.zeros(n_vars, dtype=float)
    for i, opt in enumerate(opts):
        _, hold_h = option_durations(opt)
        unit_cost = (
            float(opt.cost) + float(opt.storage_cost_fcfa_kg_day) * hold_h / 24.0
        )
        unit_full = float(opt.market.price) * values[i] - unit_cost
        unit_surplus = (
            float(opt.market.price) * float(params.delta) * values[i] - unit_cost
        )
        objective[i] = -unit_full
        objective[n + i] = -unit_surplus
    objective[2 * n] = 0.0

    a_ub: list[np.ndarray] = []
    b_ub: list[float] = []

    # Each route's own throughput limit.
    for i, opt in enumerate(opts):
        row = np.zeros(n_vars)
        row[i] = row[n + i] = 1.0
        a_ub.append(row)
        b_ub.append(float(opt.kg))

    # One full-price capacity per market, shared across all routes and storage states.
    market_groups: dict[int, list[int]] = defaultdict(list)
    market_meta: dict[int, tuple[float, float]] = {}
    for i, opt in enumerate(opts):
        market_id = int(opt.market.id)
        meta = (float(opt.market.price), float(opt.market.absorb_kg))
        if market_id in market_meta and market_meta[market_id] != meta:
            raise AllocationError(
                f"market {market_id} has inconsistent price or absorption across options"
            )
        market_meta[market_id] = meta
        market_groups[market_id].append(i)
    for market_id, indices in market_groups.items():
        row = np.zeros(n_vars)
        for i in indices:
            row[i] = values[i]
        a_ub.append(row)
        b_ub.append(market_meta[market_id][1])

    # Storage capacities are grouped by site id; an omitted id means a distinct site.
    site_groups: dict[str, list[int]] = defaultdict(list)
    site_capacities: dict[str, float] = {}
    for i, opt in enumerate(opts):
        if not opt.is_store:
            continue
        site_id = str(opt.storage_site_id or opt.id)
        capacity = float(
            opt.storage_capacity_kg if opt.storage_capacity_kg is not None else opt.kg
        )
        previous = site_capacities.get(site_id)
        if previous is not None and not np.isclose(previous, capacity):
            raise AllocationError(
                f"storage site {site_id} has inconsistent capacities; set one shared storage_capacity_kg"
            )
        site_capacities[site_id] = capacity
        site_groups[site_id].append(i)
    for site_id, indices in site_groups.items():
        row = np.zeros(n_vars)
        for i in indices:
            row[i] = row[n + i] = 1.0
        a_ub.append(row)
        b_ub.append(site_capacities[site_id])
    if store_cap is not None:
        row = np.zeros(n_vars)
        for i, opt in enumerate(opts):
            if opt.is_store:
                row[i] = row[n + i] = 1.0
        a_ub.append(row)
        b_ub.append(float(store_cap))

    a_eq = np.ones((1, n_vars), dtype=float)
    a_eq[0, : 2 * n] = 1.0
    b_eq = np.array([float(lot_kg)])
    bounds = [(0.0, None)] * n_vars
    solved = linprog(
        objective,
        A_ub=np.asarray(a_ub) if a_ub else None,
        b_ub=np.asarray(b_ub) if b_ub else None,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not solved.success or solved.x is None:
        raise AllocationError(f"allocation LP failed: {solved.message}")

    x = np.maximum(np.asarray(solved.x, dtype=float), 0.0)
    lines: list[AllocationLine] = []
    for i, opt in enumerate(opts):
        full_kg = 0.0 if x[i] < _TOL else float(x[i])
        surplus_kg = 0.0 if x[n + i] < _TOL else float(x[n + i])
        if full_kg + surplus_kg > _TOL:
            lines.append(AllocationLine(opt.id, full_kg, surplus_kg))
    allocated = sum(line.kg for line in lines)
    discarded = float(lot_kg - allocated)
    if discarded < -1e-6:
        raise AllocationError("solver returned more physical kg than the lot contains")
    discarded = max(0.0, discarded)
    if abs(allocated + discarded - lot_kg) > 1e-6:
        raise AllocationError("allocation failed mass conservation")
    return AllocationPlan(tuple(lines), discarded, float(-solved.fun))


def _lot_stub(kg: float):
    """Create only the Lot fields validated by ``validate_option`` without hiding inputs."""
    from ..contracts import Lot

    return Lot(
        kg=kg,
        maturity="breaker",
        packaging="crate",
        age_h=0.0,
        remaining_h=0.0,
        temp_c=20.0,
    )
