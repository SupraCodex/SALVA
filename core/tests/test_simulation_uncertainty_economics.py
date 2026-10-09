"""Reproducibility, validation and economic invariants for simulation."""

from dataclasses import replace

import numpy as np
import pytest
from salva_core.contracts import Lot, Market, Option, Shocks
from salva_core.params import load_product
from salva_core.simulation.economics import (
    EconomicsError,
    OptionDraws,
    evaluate,
    evaluate_portfolio,
)
from salva_core.simulation.uncertainty import ShockValidationError, draw, validate


class FixedLossModel:
    version = "test-fixed-0.1"

    def __init__(self, loss=0.2):
        self.loss = loss

    def sample_loss(self, features, u):
        return np.full(np.asarray(u).shape, self.loss, dtype=float)


def base_inputs(*, lot_kg=10.0, cap=10.0, absorption=4.0, cost=2.0):
    params = load_product("tomato")
    lot = Lot(
        kg=lot_kg,
        maturity="breaker",
        packaging="crate",
        age_h=2.0,
        remaining_h=3.0,
        temp_c=25.0,
    )
    option = Option(
        id="local",
        action="continue",
        kg=cap,
        market=Market(1, "Market A", 100.0, absorption),
        cost=cost,
    )
    shocks = Shocks(
        temp=np.zeros(100),
        transit=np.ones(100),
        price=np.ones(100),
        absorb=np.ones(100),
        u=np.linspace(0.01, 0.99, 100),
    )
    return params, lot, option, shocks


def test_draw_is_seeded_bounded_and_uses_common_length():
    a = draw(2000, 42)
    b = draw(2000, 42)
    for field in ("temp", "transit", "price", "absorb", "u"):
        assert np.array_equal(getattr(a, field), getattr(b, field))
        assert getattr(a, field).shape == (2000,)
    assert np.all(a.transit > 0) and np.all(a.price > 0) and np.all(a.absorb > 0)
    assert np.all((a.u > 0) & (a.u < 1))
    assert np.std(a.temp) == pytest.approx(1.5, rel=0.07)


@pytest.mark.parametrize("n", [0, 999, 20_001, 3.5, True])
def test_draw_rejects_invalid_draw_count(n):
    with pytest.raises(ShockValidationError):
        draw(n, 42)


@pytest.mark.parametrize("seed", [-1, 1.2, True])
def test_draw_rejects_invalid_seed(seed):
    with pytest.raises(ShockValidationError):
        draw(100, seed)


def test_shock_validation_rejects_mismatched_or_nonfinite_vectors():
    shocks = draw(1_000, 42)
    with pytest.raises(ShockValidationError):
        validate(replace(shocks, price=np.ones(99)))
    with pytest.raises(ShockValidationError):
        validate(replace(shocks, temp=np.full(100, np.nan)))
    with pytest.raises(ShockValidationError):
        validate(replace(shocks, absorb=np.zeros(100)))
    with pytest.raises(ShockValidationError):
        validate(replace(shocks, u=np.full(100, 1.1)))


def test_single_route_uses_full_price_equivalent_kg_and_discounted_surplus():
    params, lot, option, shocks = base_inputs()
    result = evaluate(FixedLossModel(), lot, option, shocks, params)
    # 10 kg * 0.8 = 8 equivalent kg; 4 at full price + 4 at the 50% surplus price.
    assert result.feasible
    assert result.loss_p10 == pytest.approx(0.2)
    assert result.loss_p50 == pytest.approx(0.2)
    assert result.loss_p90 == pytest.approx(0.2)
    assert result.recoverable_kg_p50 == pytest.approx(8.0)
    assert result.gross_value_p50 == pytest.approx(600.0)
    assert result.net_p50 == pytest.approx(580.0)
    assert result.surplus_fraction_p50 == pytest.approx(0.5)
    assert result.as_dict()["net_value_fcfa"]["p50"] == pytest.approx(580.0)
    assert "net_draws" not in result.as_dict()


def test_candidate_below_physical_capacity_is_infeasible_not_silently_partial():
    params, lot, option, shocks = base_inputs(cap=5.0)
    result = evaluate(FixedLossModel(), lot, option, shocks, params)
    assert not result.feasible
    assert result.infeasible_reason == "OPTION_CAPACITY_BELOW_LOT"
    assert result.net_p50 is None


def test_route_capacity_may_exceed_lot_without_creating_extra_quantity():
    params, lot, option, shocks = base_inputs(cap=20.0)
    result = evaluate(FixedLossModel(), lot, option, shocks, params)
    assert result.feasible
    assert result.recoverable_kg_p50 == pytest.approx(8.0)
    assert result.cost_p50 == pytest.approx(20.0)


def test_loss_model_contract_violation_is_rejected():
    params, lot, option, shocks = base_inputs()
    with pytest.raises(EconomicsError, match="loss fractions"):
        evaluate(FixedLossModel(loss=1.01), lot, option, shocks, params)


def test_unknown_action_is_rejected_before_model_execution():
    params, lot, option, shocks = base_inputs()
    with pytest.raises(EconomicsError, match="unsupported action"):
        evaluate(FixedLossModel(), lot, replace(option, action="guess"), shocks, params)


def test_direct_portfolio_evaluation_enforces_shared_storage_capacity():
    params, lot, option, shocks = base_inputs(lot_kg=6.0, cap=6.0)
    options = [
        replace(
            option,
            id="store-a",
            action="store",
            is_store=True,
            storage_mode="ambient_shade",
            storage_site_id="site",
            storage_capacity_kg=5.0,
        ),
        replace(
            option,
            id="store-b",
            action="store",
            is_store=True,
            storage_mode="ventilated",
            storage_site_id="site",
            storage_capacity_kg=5.0,
        ),
    ]
    draws = {
        o.id: OptionDraws(np.full(100, 0.2), np.full(100, 0.8), 25.0, 30.0)
        for o in options
    }
    with pytest.raises(EconomicsError, match="capacity exceeded"):
        evaluate_portfolio(
            lot,
            options,
            {"store-a": 3.0, "store-b": 3.0},
            draws,
            shocks,
            params,
            scenario_id="bad",
            action="optimized_split",
        )
