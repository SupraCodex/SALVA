"""Allocation LP: market aggregation, storage, feasibility and mass conservation."""

import numpy as np
import pytest

from salva_core.contracts import Lot, Market, Option
from salva_core.params import load_product
from salva_core.simulation.allocation import AllocationError, optimize


@pytest.fixture
def params():
    return load_product("tomato")


def opt(id, market, kg=10.0, **kw):
    return Option(id=id, action="continue", kg=kg, market=market, **kw)


def test_routes_split_at_capacity_and_mass_is_conserved(params):
    lot_kg = 10.0
    options = [
        opt("near", Market(1, "Near", 100.0, 6.0), kg=10.0),
        opt("far", Market(2, "Far", 200.0, 4.0), kg=4.0),
    ]
    plan = optimize(lot_kg, options, [1.0, 1.0], params)
    by_id = {line.option_id: line.kg for line in plan.lines}
    assert by_id == pytest.approx({"near": 6.0, "far": 4.0})
    assert plan.total_kg == pytest.approx(lot_kg)
    assert plan.discarded_kg == pytest.approx(0.0)
    assert plan.objective_fcfa == pytest.approx(1400.0)


def test_full_price_capacity_is_shared_across_routes_to_same_market(params):
    market = Market(1, "Same", 100.0, 4.0)
    options = [opt("a", market), opt("b", market)]
    plan = optimize(10.0, options, [1.0, 1.0], params)
    full_equivalent = sum(line.full_price_kg for line in plan.lines)
    surplus_physical = sum(line.surplus_kg for line in plan.lines)
    assert full_equivalent == pytest.approx(4.0)
    assert surplus_physical == pytest.approx(6.0)
    assert plan.total_kg == pytest.approx(10.0)


def test_options_at_same_storage_site_share_capacity(params):
    market = Market(1, "Market", 100.0, 100.0)
    options = [
        Option("store-a", "store", 10.0, market, is_store=True, storage_mode="ambient_shade",
               storage_site_id="site-1", storage_capacity_kg=3.0),
        Option("store-b", "store", 10.0, market, is_store=True, storage_mode="ambient_shade",
               storage_site_id="site-1", storage_capacity_kg=3.0),
        opt("continue", market, kg=10.0),
    ]
    plan = optimize(10.0, options, [1.0, 1.0, 0.8], params)
    stored = sum(line.kg for line in plan.lines if line.option_id.startswith("store-"))
    assert stored <= 3.0 + 1e-8
    assert plan.total_kg == pytest.approx(10.0)


def test_unprofitable_surplus_is_explicitly_discarded(params):
    options = [opt("loss-maker", Market(1, "Tiny market", 1.0, 0.0), cost=2.0)]
    plan = optimize(10.0, options, [0.5], params)
    assert plan.allocated_kg == pytest.approx(0.0)
    assert plan.discarded_kg == pytest.approx(10.0)
    assert plan.total_kg == pytest.approx(10.0)
    assert plan.objective_fcfa == pytest.approx(0.0)


def test_inconsistent_same_market_metadata_is_rejected(params):
    options = [opt("a", Market(1, "Market", 100.0, 20.0)),
               opt("b", Market(1, "Market", 105.0, 20.0))]
    with pytest.raises(AllocationError, match="inconsistent"):
        optimize(10.0, options, [0.8, 0.9], params)


def test_value_fractions_and_store_cap_are_validated(params):
    options = [opt("a", Market(1, "Market", 100.0, 20.0))]
    with pytest.raises(AllocationError, match="value_fractions"):
        optimize(10.0, options, [1.2], params)
    with pytest.raises(AllocationError, match="store_cap"):
        optimize(10.0, options, [0.8], params, store_cap=-1)
