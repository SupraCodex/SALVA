"""Physical properties of the kinetic model (pure functions, no I/O besides products.yaml)."""

import numpy as np
import pytest
from salva_core import features
from salva_core import kinetics as k
from salva_core.params import ProductParams, load_product


@pytest.fixture(scope="module")
def p() -> ProductParams:
    return load_product("tomato")


def test_reference_rate_and_quality(p):
    rate = k.degradation_rate(p.t_ref_c, p.t_ref_c, "breaker", 1.0, p)
    assert rate == pytest.approx(p.k_ref)  # I0(0)=1, q10**0=1, m_mat(breaker)=1
    assert k.mean_quality(rate, 168.0) == pytest.approx(np.exp(-p.k_ref * 168.0))


def test_quality_never_increases_with_time(p):
    hours = np.linspace(0, 400, 200)
    q = k.mean_quality(k.degradation_rate(25.0, 30.0, "breaker", 1.0, p), hours)
    assert np.all(np.diff(q) <= 1e-15)
    assert q[0] == 1.0


def test_quality_decreases_with_temperature(p):
    temps = np.linspace(5, 45, 100)
    q = k.mean_quality(k.degradation_rate(temps, temps + 5, "breaker", 1.0, p), 72.0)
    assert np.all(np.diff(q) < 0)


def test_loss_increases_with_time_and_temperature(p):
    h = np.linspace(0, 300, 120)
    loss_t = k.value_loss(
        k.mean_quality(k.degradation_rate(27, 32, "breaker", 1.0, p), h), "crate", p
    )
    assert np.all(np.diff(loss_t) >= -1e-12)
    t = np.linspace(10, 40, 120)
    loss_c = k.value_loss(
        k.mean_quality(k.degradation_rate(t, t + 5, "breaker", 1.0, p), 72.0),
        "crate",
        p,
    )
    assert np.all(np.diff(loss_c) >= -1e-12)


def test_diurnal_swing_accelerates_decay(p):
    flat = k.degradation_rate(25.0, 25.0, "breaker", 1.0, p)
    swing = k.degradation_rate(25.0, 33.0, "breaker", 1.0, p)
    assert swing > flat


def test_bounds(p):
    rng = np.random.default_rng(0)
    t = rng.uniform(0, 50, 5000)
    h = rng.uniform(0, 700, 5000)
    kl = np.exp(rng.normal(0, 1.0, 5000))
    q = k.mean_quality(
        k.degradation_rate(t, t + rng.uniform(0, 12, 5000), "ripe", kl, p), h
    )
    loss = k.value_loss(q, "sack", p)
    assert np.all((q > 0) & (q <= 1))
    assert np.all((loss >= 0) & (loss <= 1))


def test_grade_fractions_sum_to_one_and_extremes(p):
    q = np.array([1e-6, 0.3, 0.7, 1.0])
    frac = k.grade_fractions(q, p)
    assert np.allclose(frac.sum(axis=0), 1.0)
    assert np.all(frac >= -1e-12)
    assert frac[3, 0] > 0.99  # almost everything lost
    assert frac[0, 3] > 0.9  # almost everything grade A


def test_value_fraction_monotone_in_quality(p):
    q = np.linspace(0.01, 1.0, 300)
    assert np.all(np.diff(k.value_fraction(q, p)) >= -1e-12)


def test_quality_to_grade(p):
    assert k.quality_to_grade(0.95, p) == "A"
    assert k.quality_to_grade(0.80, p) == "A"
    assert k.quality_to_grade(0.70, p) == "B"
    assert k.quality_to_grade(0.45, p) == "C"
    assert k.quality_to_grade(0.10, p) == "D"
    with pytest.raises(ValueError):
        k.quality_to_grade(0.0, p)


def test_maturity_ordering(p):
    args = (28.0, 33.0)
    rates = [k.degradation_rate(*args, m, 1.0, p) for m in ("green", "breaker", "ripe")]
    assert rates[0] < rates[1] < rates[2]
    losses = [k.value_loss(k.mean_quality(r, 72.0), "crate", p) for r in rates]
    assert losses[0] < losses[1] < losses[2]


def test_packaging_effect(p):
    q = 0.7
    assert (
        k.value_loss(q, "crate", p)
        < k.value_loss(q, "carton", p)
        < k.value_loss(q, "sack", p)
    )


def test_deterministic(p):
    a = k.value_loss(
        k.mean_quality(k.degradation_rate(30, 35, "ripe", 1.3, p), 50.0), "sack", p
    )
    b = k.value_loss(
        k.mean_quality(k.degradation_rate(30, 35, "ripe", 1.3, p), 50.0), "sack", p
    )
    assert a == b


def test_negative_hours_rejected(p):
    with pytest.raises(ValueError):
        k.mean_quality(0.01, -1.0)


def test_unknown_category_rejected(p):
    from salva_core.params import ParamsError

    with pytest.raises(ParamsError):
        k.degradation_rate(20, 20, "rotten", 1.0, p)


def test_chilling_dose_is_cumulative_and_short_cold_hold_is_below_onset(p):
    short_hold = features.assemble(
        p,
        maturity="green",
        packaging="crate",
        age_h=0.0,
        remaining_h=0.0,
        temp_air_c=17.0,
        hold_h=72.0,
        temp_offset_c=-12.0,
        storage_mode="cold_room",
    )
    short_dose = float(k.chilling_equivalent_exposure_h(short_hold, p))
    assert short_dose == pytest.approx(72.0 * np.exp(5.0 / 7.2))
    assert short_dose < p.chilling_onset_equivalent_h["green"]
    assert k.chilling_loss_fraction_from_dose(short_dose, "green", p) == pytest.approx(
        0.0
    )

    prolonged_cold = features.assemble(
        p,
        maturity="green",
        packaging="crate",
        age_h=336.0,
        remaining_h=0.0,
        temp_air_c=2.5,
    )
    dose = float(k.chilling_equivalent_exposure_h(prolonged_cold, p))
    injury = float(k.chilling_loss_fraction_from_dose(dose, "green", p))
    assert dose > p.chilling_onset_equivalent_h["green"]
    assert injury > 0.0

    quality, loss = k.quality_and_loss(prolonged_cold, 1.0, p)
    unadjusted = float(k.value_loss(quality, "crate", p))
    assert loss == pytest.approx(1.0 - (1.0 - unadjusted) * (1.0 - injury))


def test_chilling_damage_is_monotone_in_cold_duration_and_stages(p):
    doses = np.array([0.0, 120.0, 336.0, 672.0, 1_000.0])
    green = k.chilling_loss_fraction_from_dose(doses, "green", p)
    assert np.all(np.diff(green) >= 0.0)
    assert green[0] == 0.0 and green[-1] > green[2]

    green_cold = features.assemble(
        p,
        maturity="green",
        packaging="crate",
        age_h=336.0,
        remaining_h=0.0,
        temp_air_c=2.5,
    )
    ripe_cold = features.assemble(
        p,
        maturity="ripe",
        packaging="crate",
        age_h=336.0,
        remaining_h=0.0,
        temp_air_c=2.5,
    )
    assert float(
        k.chilling_loss_fraction_from_dose(
            k.chilling_equivalent_exposure_h(green_cold, p), "green", p
        )
    ) > float(
        k.chilling_loss_fraction_from_dose(
            k.chilling_equivalent_exposure_h(ripe_cold, p), "ripe", p
        )
    )
