"""Physical properties of the kinetic model (pure functions, no I/O besides products.yaml)."""

import numpy as np
import pytest
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
