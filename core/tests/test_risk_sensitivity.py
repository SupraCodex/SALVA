"""Product-level tests for configurable risk, shelf life and sensitivity boundaries."""

from __future__ import annotations

from salva_core import features
from salva_core.contracts import LossDistribution, Lot, Market, Option
from salva_core.loss_model import KineticLossModel
from salva_core.params import load_product
from salva_core.risk import classify_risk
from salva_core.simulation import analyze_sensitivity, draw, run_all


def test_risk_uses_both_median_and_interval_width():
    params = load_product("tomato")
    low = classify_risk(LossDistribution(0.02, 0.05, 0.10), params)
    wide = classify_risk(LossDistribution(0.02, 0.05, 0.50), params)
    high_median = classify_risk(LossDistribution(0.20, 0.30, 0.32), params)
    assert low.level == "low"
    assert wide.level == "high"
    assert high_median.level == "high"
    assert wide.interval_width == 0.48


def test_kinetic_shelf_life_is_positive_and_exhausted_after_threshold():
    params = load_product("tomato")
    model = KineticLossModel(params)
    fresh = features.assemble(
        params,
        maturity="breaker",
        packaging="crate",
        age_h=0.0,
        remaining_h=0.0,
        temp_air_c=20.0,
    )
    old = features.assemble(
        params,
        maturity="breaker",
        packaging="crate",
        age_h=720.0,
        remaining_h=0.0,
        temp_air_c=35.0,
    )
    assert float(model.remaining_shelf_life_p50_h(fresh)) > 0.0
    assert float(model.remaining_shelf_life_p50_h(old)) == 0.0


def test_rm4_discourages_route_and_removes_it_from_best_probability():
    params = load_product("tomato")
    model = KineticLossModel(params)
    lot = Lot(10.0, "breaker", "crate", 0.0, 1_000.0, 35.0)
    option = Option("long", "continue", 10.0, Market(1, "market", 100.0, 100.0))
    result = run_all(model, lot, [option], draw(1_000, 4), params)[0]
    assert result.feasible
    assert result.discouraged
    assert result.discouraged_reason == "SHELF_LIFE_P50_EXCEEDED"
    assert result.prob_best == 0.0


def test_sensitivity_reuses_engine_and_reports_boundaries():
    params = load_product("tomato")
    model = KineticLossModel(params)
    lot = Lot(10.0, "breaker", "crate", 0.0, 4.0, 20.0)
    options = [
        Option("local", "sell_local", 10.0, Market(1, "local", 100.0, 100.0)),
        Option(
            "regional",
            "reroute",
            10.0,
            Market(2, "regional", 150.0, 100.0),
            extra_h=2.0,
        ),
    ]
    result = analyze_sensitivity(
        model, lot, options, params, [20.0, 35.0], [0.0, 12.0], n_draws=1_000, seed=9
    )
    assert len(result.points) == 4
    assert result.at(20.0, 0.0).risk_levels
    assert all(
        point.confidence in {"high", "medium", "low", "none"} for point in result.points
    )
    assert isinstance(result.transitions, tuple)
