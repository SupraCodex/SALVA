"""End-to-end core engine and recommendation adapter contracts."""

from dataclasses import replace

import numpy as np
import pytest

from salva_core.contracts import Lot, Market, Option
from salva_core.params import load_product
from salva_core.recommendation import Policy, recommend
from salva_core.simulation.engine import SimulationEngine, run_all
from salva_core.simulation.uncertainty import draw


class MonotoneLossModel:
    version = "test-monotone-0.1"

    def sample_loss(self, features, u):
        return np.clip(0.05 + 0.25 * np.asarray(u, dtype=float), 0, 1)


def inputs():
    p = load_product("tomato")
    lot = Lot(kg=10.0, maturity="breaker", packaging="crate", age_h=24,
              remaining_h=8, temp_c=33.0, delay_h=6.0)
    market_a = Market(1, "Local", 100.0, 5.0)
    market_b = Market(2, "Regional", 180.0, 20.0)
    options = [
        Option("local", "sell_local", 10.0, market_a, cost=2.0),
        Option("reroute", "reroute", 10.0, market_b, extra_h=2.0, cost=8.0),
    ]
    return p, lot, options


def test_p3_adapter_signatures_and_results_are_reproducible():
    p, lot, options = inputs()
    shocks = draw(500, 17)
    options[1] = replace(options[1], kg=6.0)
    first = run_all(MonotoneLossModel(), lot, options, shocks, p)
    second = run_all(MonotoneLossModel(), lot, options, shocks, p)
    assert [r.id for r in first] == [r.id for r in second]
    for a, b in zip(first, second, strict=True):
        assert np.array_equal(a.net_draws, b.net_draws)
        assert a.prob_best == pytest.approx(b.prob_best)
    assert sum(r.prob_best for r in first if r.feasible) == pytest.approx(1.0)
    assert any(r.id == "optimized_split" for r in first)
    result = recommend(first, Policy(lam=0.25, reference_value_fcfa=1800.0))
    assert hasattr(result, "best_id")
    assert result.best_id in {r.id for r in first}


def test_engine_facade_uses_same_seed_and_defaults():
    p, lot, options = inputs()
    facade = SimulationEngine(MonotoneLossModel(), p)
    a = facade.run(lot, options, n_draws=100, seed=11)
    b = facade.run(lot, options, n_draws=100, seed=11)
    assert [r.as_dict() for r in a] == [r.as_dict() for r in b]


def test_materially_tied_routes_return_no_clear_winner():
    p = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 24.0, 4.0, 25.0)
    market = Market(1, "Same market", 100.0, 100.0)
    options = [
        Option("a", "continue", 10.0, market),
        Option("b", "continue", 10.0, market),
        Option("c", "continue", 10.0, market),
    ]
    results = run_all(MonotoneLossModel(), lot, options, draw(100, 3), p, include_allocation=False)
    rec = recommend(results)
    assert rec.best_id is None
    assert rec.no_clear_winner
    assert rec.confidence == "none"
    assert "NO_CLEAR_WINNER" in rec.rationale_codes
    assert rec.ranked_ids == ("a", "b")


def test_best_action_is_risk_adjusted_and_rationales_are_structured():
    p, lot, options = inputs()
    results = run_all(MonotoneLossModel(), lot, options, draw(1000, 21), p, include_allocation=False)
    rec = recommend(results, Policy(reference_value_fcfa=1800))
    assert rec.best_id == "reroute"
    assert rec.confidence in {"high", "medium", "low"}
    assert "HIGH_TEMP" in rec.rationale_codes
    assert "DELAY" in rec.rationale_codes
    assert isinstance(rec.rationale_codes, tuple)


def test_discouraged_options_are_not_recommended():
    p, lot, options = inputs()
    results = run_all(MonotoneLossModel(), lot, options, draw(100, 6), p, include_allocation=False)
    discouraged = [replace(r, discouraged=True) for r in results]
    rec = recommend(discouraged)
    assert rec.best_id is None
    assert rec.rationale_codes == ("ALL_OPTIONS_DISCOURAGED",)


def test_one_candidate_is_named_without_inventing_a_tie():
    p, lot, options = inputs()
    results = run_all(MonotoneLossModel(), lot, options[:1], draw(100, 2), p)
    rec = recommend(results)
    assert rec.best_id == "local"
    assert rec.confidence == "high"
    assert "SINGLE_FEASIBLE_ACTION" in rec.rationale_codes


def test_invalid_policy_is_rejected():
    with pytest.raises(ValueError, match="lam"):
        Policy(lam=1.5)
