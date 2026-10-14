"""Official go/no-go criterion: agreement of the RECOMMENDED ACTION (LightGBM vs kinetic).

The simulation and recommendation engines live in salva_core (simulation, recommendation).
The adapter below calls them through their stable signatures:

    salva_core.simulation.uncertainty.draw(n, seed)               -> Shocks
    salva_core.simulation.engine.run_all(model, lot, options, S, p) -> list[result]
    salva_core.recommendation.engine.recommend(results, policy)   -> Reco (.best_id)

If they are absent or their signature differs, DecisionUnavailable is raised and the
criterion counts as NOT PASSED (verdict NO-GO).  Tests inject a fake engine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from salva_core.contracts import LossModel, Lot, Market, Option
from salva_core.params import ProductParams

Scenario = tuple[Lot, list[Option]]
DecisionFn = Callable[[LossModel, Scenario], str | None]


class DecisionUnavailable(RuntimeError):
    """P1's engines cannot be used (not delivered yet, or incompatible signature)."""


def make_scenarios(params: ProductParams, n: int, seed: int) -> list[Scenario]:
    """Random but plausible decision problems: continue / reroute / store / sell locally."""
    rng = np.random.default_rng(seed)
    out: list[Scenario] = []
    for i in range(n):
        kg = float(rng.uniform(200, 1000))
        lot = Lot(
            kg=kg, maturity=str(rng.choice(list(params.maturity))), packaging=str(rng.choice(list(params.pack_delta_c))),
            age_h=float(rng.uniform(6, 80)), remaining_h=float(rng.uniform(4, 40)),
            temp_c=float(rng.uniform(22, 33)), delay_h=0.0,
        )
        main = Market(1, "main", float(rng.uniform(600, 1000)), float(rng.uniform(0.3, 1.0) * kg))
        alt = Market(2, "alt", float(rng.uniform(500, 900)), float(rng.uniform(0.3, 1.0) * kg))
        local = Market(3, "local", float(rng.uniform(350, 650)), float(rng.uniform(0.2, 0.8) * kg))
        mode = "ventilated"
        opts = [
            Option(f"s{i}-continue", "continue", kg, main),
            # Option.cost is in FCFA per physical kg (core contract).
            Option(f"s{i}-reroute", "reroute", kg, alt, extra_h=float(rng.uniform(4, 16)), cost=15.0),
            Option(f"s{i}-store", "store", kg, main, is_store=True, storage_mode=mode, hold_h=24.0,
                   temp_offset=params.storage_offset(mode), storage_capacity_kg=200.0, cost=5.0),
            Option(f"s{i}-local", "sell_local", kg, local),
        ]
        out.append((lot, opts))
    return out


def load_p1_engine(params: ProductParams, n_draws: int = 1000, seed: int = 7) -> DecisionFn:
    try:
        from salva_core.recommendation import (
            engine as reco,  # type: ignore[import-not-found]
        )
        from salva_core.simulation import (
            engine as sim,  # type: ignore[import-not-found]
        )
        from salva_core.simulation import uncertainty  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DecisionUnavailable(f"P1 engines not available yet ({exc})") from exc

    def decide(model: LossModel, scenario: Scenario) -> str | None:
        lot, opts = scenario
        try:
            shocks = uncertainty.draw(n_draws, seed)
            results = sim.run_all(model, lot, opts, shocks, params)
            rec = reco.recommend(results, getattr(reco, "DEFAULT_POLICY", None))
        except Exception as exc:
            raise DecisionUnavailable(f"P1 engine signature mismatch: {exc!r}") from exc
        best = getattr(rec, "best_id", None)
        action = next((o.action for o in opts if o.id == best), None)
        return action

    return decide


def compute(reference: LossModel, candidate: LossModel, params: ProductParams, *, n_scenarios: int,
            seed: int, decide: DecisionFn | None = None) -> dict[str, Any]:
    decide = decide or load_p1_engine(params)
    scenarios = make_scenarios(params, n_scenarios, seed)
    agree = 0
    for sc in scenarios:
        agree += int(decide(reference, sc) == decide(candidate, sc))
    return {"status": "EVALUATED", "agreement": agree / len(scenarios), "n_scenarios": len(scenarios)}
