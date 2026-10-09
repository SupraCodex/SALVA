"""Product-level tests for configurable risk, shelf life and sensitivity boundaries."""

from __future__ import annotations

import pytest

from salva_core import features
from salva_core.contracts import LossDistribution, Lot, Market, Option
from salva_core.loss_model import KineticLossModel
from salva_core.params import load_product
from salva_core.risk import classify_risk
from salva_core.simulation import (
    analyze_parameter_sensitivity,
    analyze_sensitivity,
    draw,
    run_all,
)


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


def test_parameter_sensitivity_recomputes_recommendations_at_plus_minus_30_percent():
    params = load_product("tomato")
    model = KineticLossModel(params)
    lot = Lot(10.0, "breaker", "crate", 0.0, 4.0, 20.0)
    options = [
        Option("local", "sell_local", 10.0, Market(1, "local", 100.0, 6.0)),
        Option(
            "regional",
            "reroute",
            10.0,
            Market(2, "regional", 130.0, 8.0),
            extra_h=2.0,
        ),
    ]
    shocks = draw(1_000, 18, market_ids=[1, 2])

    result = analyze_parameter_sensitivity(
        model,
        lot,
        options,
        params,
        shocks,
        ["product.k_ref", "market:2.price"],
    )

    kinetic, price = result.points
    assert result.relative_change == pytest.approx(0.30)
    assert kinetic.baseline_value == pytest.approx(params.k_ref)
    assert kinetic.minus_value == pytest.approx(params.k_ref * 0.7)
    assert kinetic.plus_value == pytest.approx(params.k_ref * 1.3)
    assert kinetic.baseline.scores_fcfa != kinetic.minus.scores_fcfa
    assert price.baseline_value == pytest.approx(130.0)
    assert price.minus_value == pytest.approx(91.0)
    assert price.plus_value == pytest.approx(169.0)
    assert "decision_changed_plus" in result.as_dict()["points"][1]


def test_parameter_sensitivity_rejects_zero_baseline_and_out_of_domain_changes():
    params = load_product("tomato")
    model = KineticLossModel(params)
    lot = Lot(10.0, "breaker", "crate", 0.0, 4.0, 20.0)
    options = [Option("local", "sell_local", 10.0, Market(1, "local", 100.0, 100.0))]

    with pytest.raises(ValueError, match="non-zero baseline"):
        analyze_parameter_sensitivity(
            model,
            lot,
            options,
            params,
            draw(1_000, 9, market_ids=[1]),
            ["option:local.cost"],
        )
    with pytest.raises(ValueError, match="perturbed q10 must be >= 1"):
        analyze_parameter_sensitivity(
            model,
            lot,
            options,
            params,
            draw(1_000, 9, market_ids=[1]),
            ["product.q10"],
            relative_change=0.8,
        )
