"""Feature construction: values, units, limits, invalid inputs, shared schema."""

import numpy as np
import pytest
from salva_core import features as F
from salva_core import kinetics as K
from salva_core.contracts import Lot, Market, Option, Shocks
from salva_core.params import load_product
from scipy.special import i0


@pytest.fixture(scope="module")
def p():
    return load_product("tomato")


def base(p, **kw):
    args = {
        "maturity": "breaker",
        "packaging": "crate",
        "age_h": 50,
        "remaining_h": 18,
        "delay_h": 12,
        "temp_air_c": 29,
    }
    args.update(kw)
    return F.assemble(p, **args)


def test_values_and_units(p):
    f = base(p)
    assert f.temp_mean_c == 29.0  # crate: no packaging delta
    assert f.temp_max_c == 29.0 + p.default_diurnal_amp_c
    assert f.exposure_h == 68.0 and f.remaining_transit_h == 18.0
    assert f.degree_hours_above_ref == pytest.approx((29.0 - p.t_ref_c) * 68.0)
    assert f.delay_h == 12.0 and f.storage_mode == "none"


def test_packaging_and_storage_offsets(p):
    sack = base(p, packaging="sack")
    assert sack.temp_mean_c == pytest.approx(29.0 + p.pack_delta_c["sack"])
    cold = base(
        p,
        hold_h=12.0,
        temp_offset_c=p.storage_offset("cold_room"),
        storage_mode="cold_room",
    )
    assert cold.temp_mean_c == pytest.approx((29.0 * 68.0 + 17.0 * 12.0) / 80.0)
    assert cold.temp_max_c == pytest.approx(34.0)  # transit, not the cold hold
    assert cold.remaining_transit_h == pytest.approx(18.0)
    assert cold.hold_h == pytest.approx(12.0)
    assert cold.exposure_h == pytest.approx(80.0)
    assert cold.degree_hours_above_ref == pytest.approx(9.0 * 68.0)
    assert cold.thermal_rate_factor == pytest.approx(
        (68.0 * p.q10**0.9 * i0(5.0 * np.log(p.q10) / 10.0) + 12.0 * p.q10 ** (-0.3))
        / 80.0
    )
    expected_quality = np.exp(
        -p.k_ref
        * (68.0 * p.q10**0.9 * i0(5.0 * np.log(p.q10) / 10.0) + 12.0 * p.q10**-0.3)
    )
    actual_quality, _ = K.quality_and_loss(cold, 1.0, p)
    assert actual_quality == pytest.approx(expected_quality)


def test_storage_offset_does_not_change_historical_or_transit_phase(p):
    f = base(
        p,
        age_h=0.0,
        remaining_h=10.0,
        delay_h=0.0,
        temp_air_c=29.0,
        temp_shock_c=2.0,
        transit_factor=1.5,
        extra_h=2.0,
        hold_h=10.0,
        temp_offset_c=-12.0,
        storage_mode="cold_room",
    )
    transit_rate_factor = p.q10**1.1 * i0(5.0 * np.log(p.q10) / 10.0)
    hold_rate_factor = p.q10**-0.1
    assert f.remaining_transit_h == pytest.approx(18.0)
    assert f.hold_h == pytest.approx(10.0)
    assert f.exposure_h == pytest.approx(28.0)
    assert f.temp_mean_c == pytest.approx((31.0 * 18.0 + 19.0 * 10.0) / 28.0)
    assert f.degree_hours_above_ref == pytest.approx(11.0 * 18.0)
    assert f.thermal_rate_factor == pytest.approx(
        (transit_rate_factor * 18.0 + hold_rate_factor * 10.0) / 28.0
    )


def test_zero_hold_has_no_storage_temperature_or_category_effect(p):
    f = base(
        p,
        hold_h=0.0,
        temp_offset_c=p.storage_offset("cold_room"),
        storage_mode="cold_room",
    )
    assert f.storage_mode == "none"
    assert f.temp_mean_c == pytest.approx(29.0)
    assert f.storage_temp_mean_c == pytest.approx(f.transit_temp_mean_c)


def test_extra_hours_and_transit_factor(p):
    f = base(p, extra_h=6, transit_factor=1.5)
    assert f.remaining_transit_h == pytest.approx((18 + 6) * 1.5)
    assert f.exposure_h == pytest.approx(50 + 36)


def test_arrays_broadcast(p):
    f = base(
        p,
        temp_shock_c=np.array([-1.0, 0.0, 1.0]),
        transit_factor=np.array([0.9, 1.0, 1.1]),
    )
    assert f.temp_mean_c.shape == (3,) and F.n_rows(f) == 3
    assert F.to_matrix(f).shape == (3, len(F.MODEL_COLUMNS))


def test_limit_values_accepted(p):
    f = base(p, age_h=0, remaining_h=0, delay_h=0, temp_air_c=0.0)
    assert f.exposure_h == 0.0 and f.degree_hours_above_ref == 0.0
    f = base(p, temp_air_c=50.0)
    assert f.temp_mean_c >= 50.0


@pytest.mark.parametrize(
    "kw",
    [
        {"age_h": -1},
        {"remaining_h": -1},
        {"extra_h": -1},
        {"hold_h": -1},
        {"delay_h": -1},
        {"delay_h": 30.0},
        {"temp_air_c": -5.0},
        {"temp_air_c": 80.0},
        {"transit_factor": 0.0},
        {"diurnal_amp_c": -1.0},
        {"age_h": float("nan")},
        {"age_h": float("inf")},
    ],
)
def test_invalid_inputs_rejected(p, kw):
    with pytest.raises(ValueError):
        base(p, **kw)


@pytest.mark.parametrize(
    "kw", [{"maturity": "rotten"}, {"packaging": "bag"}, {"storage_mode": "fridge"}]
)
def test_unknown_categories_rejected(p, kw):
    with pytest.raises(ValueError):
        base(p, **kw)


def test_build_matches_assemble(p):
    lot = Lot(
        kg=500,
        maturity="breaker",
        packaging="crate",
        age_h=50,
        remaining_h=18,
        temp_c=29.0,
        delay_h=12.0,
    )
    opt = Option(
        id="c", action="continue", kg=500, market=Market(1, "Douala", 800, 250)
    )
    s = Shocks(
        temp=np.array([0.5]),
        transit=np.array([1.1]),
        price=np.ones(1),
        absorb=np.ones(1),
        u=np.array([0.5]),
    )
    a = F.build(lot, opt, s, p)
    b = base(p, temp_shock_c=0.5, transit_factor=1.1)
    assert np.allclose(F.to_matrix(a), F.to_matrix(b))


def test_build_distinguishes_legacy_store_hold_from_new_detour_and_hold(p):
    lot = Lot(10.0, "breaker", "crate", 4.0, 6.0, 29.0)
    market = Market(1, "Local", 100.0, 100.0)
    shocks = Shocks(
        temp=np.zeros(1),
        transit=np.ones(1),
        price=np.ones(1),
        absorb=np.ones(1),
        u=np.array([0.5]),
    )
    legacy = Option(
        "legacy-store",
        "store",
        10.0,
        market,
        extra_h=12.0,
        is_store=True,
        storage_mode="ambient_shade",
    )
    explicit = Option(
        "explicit-store",
        "store",
        10.0,
        market,
        extra_h=2.0,
        is_store=True,
        storage_mode="ambient_shade",
        hold_h=12.0,
    )

    old_features = F.build(lot, legacy, shocks, p)
    new_features = F.build(lot, explicit, shocks, p)

    assert old_features.remaining_transit_h == pytest.approx(6.0)
    assert old_features.hold_h == pytest.approx(12.0)
    assert new_features.remaining_transit_h == pytest.approx(8.0)
    assert new_features.hold_h == pytest.approx(12.0)
    assert new_features.exposure_h == pytest.approx(24.0)


def test_with_changes_recomputes_derived(p):
    f = base(p)
    g = F.with_changes(f, p, temp_mean_c=33.0, age_h=60.0)
    assert g.temp_max_c - g.temp_mean_c == pytest.approx(f.temp_max_c - f.temp_mean_c)
    assert g.exposure_h == pytest.approx(60.0 + 18.0)
    assert g.degree_hours_above_ref == pytest.approx((33.0 - p.t_ref_c) * 78.0)
    with pytest.raises(ValueError):
        F.with_changes(f, p, kg=3)
    with pytest.raises(ValueError, match="delay_h"):
        F.with_changes(f, p, remaining_transit_h=4.0, delay_h=5.0)


def test_weather_route_draw_shorter_than_delay_still_allows_other_counterfactuals(p):
    f = base(
        p,
        age_h=0.0,
        remaining_h=10.0,
        delay_h=8.0,
        transit_factor=0.5,
    )
    assert f.remaining_transit_h == pytest.approx(5.0)
    assert F.with_changes(f, p, temp_mean_c=30.0).temp_mean_c == pytest.approx(30.0)
    with pytest.raises(ValueError, match="delay_h"):
        F.with_changes(f, p, remaining_transit_h=4.0)


def test_with_changes_preserves_and_recomputes_storage_phases(p):
    f = base(
        p,
        age_h=10.0,
        remaining_h=5.0,
        delay_h=0.0,
        hold_h=5.0,
        temp_offset_c=-10.0,
        storage_mode="cold_room",
    )
    g = F.with_changes(f, p, age_h=20.0, hold_h=10.0)
    assert g.exposure_h == pytest.approx(35.0)
    assert g.temp_mean_c == pytest.approx((25.0 * 29.0 + 10.0 * 19.0) / 35.0)
    assert g.degree_hours_above_ref == pytest.approx(9.0 * 25.0)
    assert g.thermal_rate_factor != pytest.approx(f.thermal_rate_factor)

    targeted = F.with_changes(f, p, age_h=20.0, hold_h=10.0, temp_mean_c=30.0)
    assert targeted.temp_mean_c == pytest.approx(30.0)


def test_encoding_roundtrip_and_schema(p):
    f = base(
        p,
        maturity="ripe",
        packaging="sack",
        storage_mode="ventilated",
        hold_h=3.0,
    )
    row = F.to_matrix(f)[0]
    cols = list(F.MODEL_COLUMNS)
    assert row[cols.index("maturity")] == F.MATURITY_CODES["ripe"]
    assert row[cols.index("packaging")] == F.PACKAGING_CODES["sack"]
    assert row[cols.index("storage_mode")] == F.STORAGE_CODES["ventilated"]
    assert len(F.schema_hash()) == 64
    cols_dict = {c: np.array([getattr(f, c)]) for c in F.MODEL_COLUMNS}
    g = F.from_arrays(cols_dict)
    assert np.allclose(F.to_matrix(g), F.to_matrix(f))
    with pytest.raises(ValueError):
        F.from_arrays({"age_h": [1.0]})


def test_from_arrays_clears_storage_mode_without_hold(p):
    f = base(p, hold_h=0.0)
    columns = {name: np.array([getattr(f, name)]) for name in F.MODEL_COLUMNS}
    columns["storage_mode"] = np.array(["cold_room"], dtype=object)

    rebuilt = F.from_arrays(columns)

    assert rebuilt.storage_mode.tolist() == ["none"]
    assert F.to_matrix(rebuilt)[0, F.MODEL_COLUMNS.index("storage_mode")] == 0.0
