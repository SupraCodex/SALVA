"""End-to-end core engine and recommendation adapter contracts."""

from dataclasses import replace

import numpy as np
import pytest
import salva_core.simulation.engine as engine_module
from salva_core.contracts import Lot, Market, Option
from salva_core.loss_model import KineticLossModel
from salva_core.params import load_product
from salva_core.recommendation import Policy, recommend
from salva_core.simulation.engine import SimulationEngine, run_all
from salva_core.simulation.uncertainty import draw


class MonotoneLossModel:
    version = "test-monotone-0.1"

    def sample_loss(self, features, u):
        return np.clip(0.05 + 0.25 * np.asarray(u, dtype=float), 0, 1)


class FixedShelfLifeModel(MonotoneLossModel):
    def remaining_shelf_life_p50_h(self, features):
        return 10.0


def inputs():
    p = load_product("tomato")
    lot = Lot(
        kg=10.0,
        maturity="breaker",
        packaging="crate",
        age_h=24,
        remaining_h=8,
        temp_c=33.0,
        delay_h=6.0,
    )
    market_a = Market(1, "Local", 100.0, 5.0)
    market_b = Market(2, "Regional", 180.0, 20.0)
    options = [
        Option("local", "sell_local", 10.0, market_a, cost=2.0),
        Option("reroute", "reroute", 10.0, market_b, extra_h=2.0, cost=8.0),
    ]
    return p, lot, options


def test_p3_adapter_signatures_and_results_are_reproducible():
    p, lot, options = inputs()
    shocks = draw(1_000, 17)
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
    a = facade.run(lot, options, n_draws=1_000, seed=11)
    b = facade.run(lot, options, n_draws=1_000, seed=11)
    assert [r.as_dict() for r in a] == [r.as_dict() for r in b]


def test_engine_facade_requests_market_specific_shocks(monkeypatch):
    p, lot, options = inputs()
    requested: list[set[int]] = []
    real_draw = engine_module.draw

    def capture_draw(n, seed, *, market_ids=()):
        requested.append(set(market_ids))
        return real_draw(n, seed, market_ids=market_ids)

    monkeypatch.setattr(engine_module, "draw", capture_draw)
    SimulationEngine(MonotoneLossModel(), p).run(lot, options, n_draws=100, seed=11)

    assert requested == [{1, 2}]


def test_engine_facade_accepts_minimum_one_hundred_draws():
    p, lot, options = inputs()
    facade = SimulationEngine(MonotoneLossModel(), p)
    results = facade.run(lot, options, n_draws=100, seed=11)
    assert results


def test_run_all_rejects_fewer_than_one_hundred_draws():
    p, lot, options = inputs()
    full = draw(100, 11)
    short = replace(
        full,
        temp=full.temp[:99],
        transit=full.transit[:99],
        price=full.price[:99],
        absorb=full.absorb[:99],
        u=full.u[:99],
    )
    with pytest.raises(ValueError, match="at least 100"):
        run_all(MonotoneLossModel(), lot, options, short, p)


def test_missing_market_absorption_requires_upstream_default_resolution():
    p, lot, options = inputs()
    options[0] = replace(
        options[0],
        market=Market(1, "Local", 100.0, None),  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="market price and absorb_kg must be supplied"):
        run_all(MonotoneLossModel(), lot, options, draw(1_000, 19), p)


def test_real_kinetic_model_runs_two_thousand_draws_end_to_end():
    p, lot, options = inputs()
    results = SimulationEngine(KineticLossModel(p), p).run(
        lot, options, n_draws=2_000, seed=42
    )
    assert results
    for result in results:
        if result.feasible:
            assert result.loss_p10 <= result.loss_p50 <= result.loss_p90
            assert result.net_p10 <= result.net_p50 <= result.net_p90
    eligible = [r for r in results if r.feasible and not r.discouraged]
    if eligible:
        assert sum(r.prob_best for r in eligible) == pytest.approx(1.0)
    else:
        assert all(r.prob_best == 0.0 for r in results)
        assert any(r.discouraged for r in results if r.feasible)


def test_rm4_counts_storage_hold_separately_from_transit():
    p = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 0.0, 8.0, 25.0)
    option = Option(
        "store",
        "store",
        10.0,
        Market(1, "Local", 100.0, 100.0),
        is_store=True,
        storage_mode="ambient_shade",
        hold_h=3.0,
    )

    result = run_all(FixedShelfLifeModel(), lot, [option], draw(1_000, 31), p)[0]

    assert result.discouraged
    assert result.discouraged_reason == "SHELF_LIFE_P50_EXCEEDED"
    assert result.extra_h == 0.0
    assert result.hold_h == 3.0
    assert result.as_dict()["hold_h"] == 3.0


def test_storage_mode_default_offset_reaches_shelf_life_model():
    p = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 0.0, 8.0, 25.0)
    option = Option(
        "cold-store",
        "store",
        10.0,
        Market(1, "Local", 100.0, 100.0),
        is_store=True,
        storage_mode="cold_room",
        hold_h=3.0,
    )
    result = run_all(FixedShelfLifeModel(), lot, [option], draw(1_000, 39), p)[0]

    assert result.temp_mean_c == pytest.approx((25.0 * 8.0 + 13.0 * 3.0) / 11.0)


def test_high_temp_reason_uses_nominal_mean_and_strict_threshold():
    p = load_product("tomato")
    # Air at 30 C plus crate offset 0 C; diurnal maximum does not redefine T in HIGH_TEMP.
    lot = Lot(10.0, "breaker", "crate", 24.0, 4.0, 30.0)
    option = Option("continue", "continue", 10.0, Market(1, "Market", 100.0, 20.0))
    result = run_all(MonotoneLossModel(), lot, [option], draw(1_000, 44), p)[0]
    recommendation = recommend([result])
    assert result.temp_mean_c == pytest.approx(30.0)
    assert "HIGH_TEMP" not in recommendation.rationale_codes


def test_materially_tied_routes_return_no_clear_winner():
    p = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 24.0, 4.0, 25.0)
    market = Market(1, "Same market", 100.0, 100.0)
    options = [
        Option("a", "continue", 10.0, market),
        Option("b", "continue", 10.0, market),
        Option("c", "continue", 10.0, market),
    ]
    results = run_all(
        MonotoneLossModel(), lot, options, draw(1_000, 3), p, include_allocation=False
    )
    rec = recommend(results)
    assert rec.best_id is None
    assert rec.no_clear_winner
    assert rec.confidence == "low"
    assert "NO_CLEAR_WINNER" in rec.rationale_codes
    assert rec.ranked_ids == ("a", "b")


def test_default_materiality_uses_nominal_lot_value_not_net_score():
    p = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 24.0, 4.0, 25.0)
    market = Market(1, "Same market", 100.0, 100.0)
    options = [
        Option(option_id, "continue", 10.0, market) for option_id in ("a", "b", "c")
    ]
    results = run_all(
        MonotoneLossModel(), lot, options, draw(1_000, 13), p, include_allocation=False
    )
    assert all(r.lot_reference_value_fcfa == pytest.approx(1_000.0) for r in results)
    # A four-FCFA score gap is 0.4% of the nominal 1,000 FCFA lot value, but 4% of
    # the leading 100-FCFA net score. The specified 3% lot-value threshold must win.
    results = [
        replace(
            row,
            net_p10=score - 1.0,
            net_p50=score,
            net_p90=score + 1.0,
            prob_best=1.0 / 3.0,
        )
        for row, score in zip(results, (100.0, 96.0, 92.0), strict=True)
    ]
    rec = recommend(results)
    assert rec.no_clear_winner
    assert rec.best_id is None
    assert rec.confidence == "low"
    assert rec.gap_fraction == pytest.approx(0.004)


def test_best_action_is_risk_adjusted_and_rationales_are_structured():
    p, lot, options = inputs()
    results = run_all(
        MonotoneLossModel(), lot, options, draw(1000, 21), p, include_allocation=False
    )
    rec = recommend(results, Policy(reference_value_fcfa=1800))
    assert rec.best_id == "reroute"
    assert rec.confidence in {"high", "medium", "low"}
    assert "HIGH_TEMP" in rec.rationale_codes
    assert "DELAY" in rec.rationale_codes
    assert isinstance(rec.rationale_codes, tuple)


def test_discouraged_options_are_not_recommended():
    p, lot, options = inputs()
    results = run_all(
        MonotoneLossModel(), lot, options, draw(1_000, 6), p, include_allocation=False
    )
    discouraged = [replace(r, discouraged=True) for r in results]
    rec = recommend(discouraged)
    assert rec.best_id is None
    assert rec.rationale_codes == ("ALL_OPTIONS_DISCOURAGED",)


def test_one_candidate_is_named_without_inventing_a_tie():
    p, lot, options = inputs()
    results = run_all(MonotoneLossModel(), lot, options[:1], draw(1_000, 2), p)
    rec = recommend(results)
    assert rec.best_id == "local"
    assert rec.confidence == "medium"
    assert rec.gap_fraction is None  # no second option exists for a comparative gap
    assert "SINGLE_FEASIBLE_ACTION" in rec.rationale_codes


def test_recommendation_rejects_missing_or_crossed_net_p90():
    from dataclasses import replace

    p, lot, options = inputs()
    results = run_all(MonotoneLossModel(), lot, options[:1], draw(1_000, 8), p)
    with pytest.raises(ValueError, match="P10/P50/P90"):
        recommend([replace(results[0], net_p90=None)])
    with pytest.raises(ValueError, match="P10 <= P50 <= P90"):
        recommend([replace(results[0], net_p90=results[0].net_p50 - 1.0)])


def test_invalid_policy_is_rejected():
    with pytest.raises(ValueError, match="lam"):
        Policy(lam=1.5)
