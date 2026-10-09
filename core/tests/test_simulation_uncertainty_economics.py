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


def test_market_shocks_are_independent_seeded_and_stable_by_market_id():
    legacy = draw(2_000, 42)
    first = draw(2_000, 42, market_ids=[11, 22])
    reordered = draw(2_000, 42, market_ids=[22, 11])

    for name in ("temp", "transit", "price", "absorb", "u"):
        assert np.array_equal(getattr(legacy, name), getattr(first, name))
    assert first.price_by_market is not None
    assert first.absorb_by_market is not None
    for market_id in (11, 22):
        assert np.array_equal(
            first.price_by_market[market_id], reordered.price_by_market[market_id]
        )
        assert np.array_equal(
            first.absorb_by_market[market_id], reordered.absorb_by_market[market_id]
        )
    assert (
        abs(np.corrcoef(first.price_by_market[11], first.price_by_market[22])[0, 1])
        < 0.08
    )
    assert (
        abs(np.corrcoef(first.absorb_by_market[11], first.absorb_by_market[22])[0, 1])
        < 0.08
    )


def test_market_shock_validation_rejects_bad_market_vectors():
    shocks = draw(100, 42, market_ids=[1])
    with pytest.raises(ShockValidationError, match=r"shape \(100,\)"):
        validate(replace(shocks, price_by_market={1: np.ones(99)}))
    with pytest.raises(ShockValidationError, match="finite positive multipliers"):
        validate(replace(shocks, absorb_by_market={1: np.zeros(100)}))
    with pytest.raises(ShockValidationError, match="integer market ids"):
        validate(replace(shocks, price_by_market={True: np.ones(100)}))


@pytest.mark.parametrize("n", [0, 99, 20_001, 3.5, True])
def test_draw_rejects_invalid_draw_count(n):
    with pytest.raises(ShockValidationError):
        draw(n, 42)


@pytest.mark.parametrize("n", [100, 20_000])
def test_draw_accepts_configured_boundary_counts(n):
    assert draw(n, 42).u.shape == (n,)


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


def test_portfolio_uses_market_specific_price_and_absorption_draws():
    params, lot, option, shocks = base_inputs(
        lot_kg=10.0, cap=10.0, absorption=4.0, cost=0.0
    )
    second_market = replace(
        option,
        id="regional",
        kg=10.0,
        market=Market(2, "Market B", 100.0, 4.0),
    )
    options = [option, second_market]
    draws = {
        item.id: OptionDraws(np.full(100, 0.2), np.full(100, 0.8), 25.0, 30.0)
        for item in options
    }
    shocks = replace(
        shocks,
        price_by_market={1: np.full(100, 2.0), 2: np.ones(100)},
        absorb_by_market={1: np.full(100, 0.5), 2: np.full(100, 2.0)},
    )

    result = evaluate_portfolio(
        lot,
        options,
        {"local": 5.0, "regional": 5.0},
        draws,
        shocks,
        params,
        scenario_id="two-markets",
        action="optimized_split",
    )

    # Market 1: 4 equivalent kg at price x2, with only 2 at full price; 600 FCFA.
    # Market 2: 4 equivalent kg at base price, all below its market-specific cap; 400 FCFA.
    assert result.gross_value_p50 == pytest.approx(1_000.0)


def test_portfolio_rejects_overflowed_market_economic_draws():
    params, lot, option, shocks = base_inputs(absorption=100.0, cost=0.0)
    option = replace(option, market=Market(1, "Huge", 1e308, 100.0))
    shocks = replace(shocks, price_by_market={1: np.full(100, 1e308)})
    od = OptionDraws(np.full(100, 0.0), np.full(100, 1.0), 25.0, 30.0)

    with pytest.raises(
        EconomicsError, match="portfolio economic draws must all be finite"
    ):
        evaluate_portfolio(
            lot,
            [option],
            {option.id: lot.kg},
            {option.id: od},
            shocks,
            params,
            scenario_id="overflow",
            action=option.action,
        )


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


def test_storage_tariff_is_charged_per_physical_kg_and_day():
    params, lot, option, shocks = base_inputs(absorption=100.0)
    store = replace(
        option,
        action="store",
        is_store=True,
        storage_mode="ambient_shade",
        hold_h=48.0,
        storage_cost_fcfa_kg_day=3.0,
    )

    result = evaluate(FixedLossModel(), lot, store, shocks, params)

    # 10 physical kg * (2 FCFA/kg route cost + 3 * 2 days storage).
    assert result.cost_p50 == pytest.approx(80.0)
    assert result.net_p50 == pytest.approx(result.gross_value_p50 - 80.0)


def test_route_transport_and_storage_costs_are_composed_once():
    params, lot, option, shocks = base_inputs(absorption=100.0)
    route = replace(
        option,
        action="store",
        is_store=True,
        storage_mode="ambient_shade",
        hold_h=48.0,
        transport_distance_km=5.0,
        transport_cost_fcfa_kg_km=1.5,
        storage_cost_fcfa_kg_day=3.0,
    )

    result = evaluate(FixedLossModel(), lot, route, shocks, params)

    # Per kg: 2 route + (5 km * 1.5) transport + (2 days * 3) storage.
    assert result.cost_p50 == pytest.approx(155.0)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"storage_cost_fcfa_kg_day": -1.0}, "finite and >= 0"),
        ({"storage_cost_fcfa_kg_day": float("inf")}, "finite and >= 0"),
        ({"storage_cost_fcfa_kg_day": True}, "numeric, not bool"),
        ({"cost": True}, "numeric, not bool"),
        ({"transport_distance_km": True}, "numeric, not bool"),
        (
            {
                "transport_distance_km": 1e308,
                "transport_cost_fcfa_kg_km": 1e308,
            },
            "calculated unit cost must be finite",
        ),
        ({"storage_cost_fcfa_kg_day": 1.0}, "requires storage"),
        (
            {
                "action": "store",
                "is_store": True,
                "storage_mode": "ambient_shade",
                "storage_cost_fcfa_kg_day": 1.0,
            },
            "requires hold_h > 0",
        ),
    ],
)
def test_storage_tariff_rejects_invalid_or_nonstorage_use(changes, message):
    params, lot, option, shocks = base_inputs()
    with pytest.raises(EconomicsError, match=message):
        evaluate(FixedLossModel(), lot, replace(option, **changes), shocks, params)


def test_loss_model_contract_violation_is_rejected():
    params, lot, option, shocks = base_inputs()
    with pytest.raises(EconomicsError, match="loss fractions"):
        evaluate(FixedLossModel(loss=1.01), lot, option, shocks, params)


def test_unknown_action_is_rejected_before_model_execution():
    params, lot, option, shocks = base_inputs()
    with pytest.raises(EconomicsError, match="unsupported action"):
        evaluate(FixedLossModel(), lot, replace(option, action="guess"), shocks, params)


def test_hold_duration_is_storage_only_and_rejects_boolean_values():
    params, lot, option, shocks = base_inputs()
    with pytest.raises(EconomicsError, match="requires storage"):
        evaluate(FixedLossModel(), lot, replace(option, hold_h=2.0), shocks, params)
    store = replace(
        option,
        action="store",
        is_store=True,
        storage_mode="ambient_shade",
        hold_h=True,  # type: ignore[arg-type]
    )
    with pytest.raises(EconomicsError, match="not bool"):
        evaluate(FixedLossModel(), lot, store, shocks, params)


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


@pytest.mark.parametrize(
    ("draw_changes", "message"),
    [
        ({"loss": np.full(100, 1.01)}, r"loss draws.*finite in \[0, 1\]"),
        (
            {"value_fraction": np.full(100, 0.7)},
            "value fractions.*equal 1 - loss",
        ),
        (
            {"value_fraction": np.full(100, np.nan)},
            r"value fractions.*finite in \[0, 1\]",
        ),
        ({"temp_mean_c": float("inf")}, "temperatures.*finite"),
    ],
)
def test_direct_portfolio_rejects_invalid_loss_model_draws(draw_changes, message):
    params, lot, option, shocks = base_inputs(absorption=100.0)
    base = OptionDraws(np.full(100, 0.2), np.full(100, 0.8), 25.0, 30.0)
    invalid = replace(base, **draw_changes)

    with pytest.raises(EconomicsError, match=message):
        evaluate_portfolio(
            lot,
            [option],
            {option.id: lot.kg},
            {option.id: invalid},
            shocks,
            params,
            scenario_id="invalid",
            action=option.action,
        )
