"""Kinetic quality model (pure, deterministic, vectorised).

Mean quality of a lot after ``hours`` of exposure:

    k = k_ref * q10 ** ((T_mean - T_ref) / 10) * I0(A * ln(q10) / 10) * m_mat * k_lot
    Q = exp(-k * hours)                                   Q in (0, 1]

* T_mean: effective mean product temperature (degC); A = T_max - T_mean >= 0 is the
  half amplitude of the daily cycle.  Averaging the Q10 law over a sinusoidal day gives
  the exact factor I0(A ln(q10) / 10), where I0 is the modified Bessel function of order 0.
  It is >= 1: temperature swings accelerate decay for the same mean temperature.
* m_mat: maturity multiplier; k_lot: lot-to-lot multiplier (lognormal, see
  loss_model.kinetic_model).

Individual fruit quality is lognormal around Q:  q_i = Q * exp(sigma_h * eps).
Fruits are graded A/B/C/D by thresholds, each grade has a price multiplier, and
packaging causes an immediate multiplicative damage.  The *loss* of a lot is
``1 - value_fraction * (1 - pack_damage)``.

No network, no database, no web framework, no LLM.  All constants come from
ProductParams (data/reference/products.yaml); they are starting points, not results.
"""

from __future__ import annotations

import numpy as np
from scipy.special import i0, ndtr

from .contracts import ConditionFeatures
from .params import ProductParams, lookup

_EPS = 1e-12
GRADE_NAMES = ("A", "B", "C", "D")


def thermal_factor(temp_mean_c, temp_max_c, p: ProductParams):
    """Acceleration of decay vs reference: Q10 law averaged over the daily cycle."""
    t_mean = np.asarray(temp_mean_c, dtype=float)
    amp = np.maximum(np.asarray(temp_max_c, dtype=float) - t_mean, 0.0)
    q10_term = p.q10 ** ((t_mean - p.t_ref_c) / 10.0)
    return q10_term * i0(amp * np.log(p.q10) / 10.0)


def chilling_equivalent_exposure_h(
    f: ConditionFeatures,
    p: ProductParams,
    *,
    phase: str = "all",
) -> np.ndarray:
    """Return cumulative below-threshold exposure in threshold-equivalent hours.

    The exponential temperature weighting maps about seven days at 5 C to fourteen
    days at 10 C for mature-green tomatoes. The scale and onset are product assumptions,
    not a universal cultivar response. Missing phase metadata (for rows reconstructed
    from model matrices) falls back to the reported mean temperature for each phase.
    ``phase`` may be ``historical``, ``future`` or ``all``.
    """
    if phase not in {"historical", "future", "all"}:
        raise ValueError("phase must be 'historical', 'future' or 'all'")
    fallback = np.asarray(f.temp_mean_c, dtype=float)
    temperatures = (
        np.asarray(
            f.history_temp_mean_c if f.history_temp_mean_c is not None else fallback,
            dtype=float,
        ),
        np.asarray(
            f.transit_temp_mean_c if f.transit_temp_mean_c is not None else fallback,
            dtype=float,
        ),
        np.asarray(
            f.storage_temp_mean_c if f.storage_temp_mean_c is not None else fallback,
            dtype=float,
        ),
    )
    durations = (
        np.asarray(f.age_h, dtype=float),
        np.asarray(f.remaining_transit_h, dtype=float),
        np.asarray(f.hold_h, dtype=float),
    )
    threshold = np.asarray(lookup(p.chilling_threshold_c, f.maturity, "maturity"))
    temps_and_durations = np.broadcast_arrays(*temperatures, *durations, threshold)
    hist_temp, transit_temp, storage_temp, age, transit, hold, limit = (
        np.asarray(value, dtype=float) for value in temps_and_durations
    )
    selected = {
        "historical": ((hist_temp, age),),
        "future": ((transit_temp, transit), (storage_temp, hold)),
        "all": ((hist_temp, age), (transit_temp, transit), (storage_temp, hold)),
    }[phase]
    dose = np.zeros_like(limit, dtype=float)
    for temp, hours in selected:
        below = np.maximum(limit - temp, 0.0)
        weighted_hours = hours * np.exp(
            np.clip(below / p.chilling_temperature_scale_c, 0.0, 40.0)
        )
        dose += np.where((temp < limit) & (hours > 0.0), weighted_hours, 0.0)
    return dose


def chilling_loss_fraction_from_dose(dose_equivalent_h, maturity, p: ProductParams):
    """Return the assumed post-onset fraction of value lost to chilling injury."""
    dose = np.asarray(dose_equivalent_h, dtype=float)
    onset = np.asarray(
        lookup(p.chilling_onset_equivalent_h, maturity, "maturity"), dtype=float
    )
    excess = np.maximum(dose - onset, 0.0)
    return np.clip(-np.expm1(-p.chilling_loss_rate_per_equivalent_h * excess), 0.0, 1.0)


def apply_chilling_penalty(loss, f: ConditionFeatures, p: ProductParams):
    """Compose the deterministic chilling-value penalty with any model loss fraction."""
    base_loss = np.asarray(loss, dtype=float)
    injury = np.asarray(
        chilling_loss_fraction_from_dose(
            chilling_equivalent_exposure_h(f, p), f.maturity, p
        ),
        dtype=float,
    )
    while injury.ndim < base_loss.ndim:
        injury = np.expand_dims(injury, axis=-1)
    return np.clip(1.0 - (1.0 - base_loss) * (1.0 - injury), 0.0, 1.0)


def degradation_rate(temp_mean_c, temp_max_c, maturity, k_lot, p: ProductParams):
    """Decay rate k (1/h) of the mean quality."""
    m_mat = lookup(p.maturity, maturity, "maturity")
    return (
        p.k_ref * thermal_factor(temp_mean_c, temp_max_c, p) * m_mat * np.asarray(k_lot)
    )


def degradation_rate_for_features(f, k_lot, p: ProductParams):
    """Decay rate using phase-integrated Q10 factors when the builder provides them."""
    factor = getattr(f, "thermal_rate_factor", None)
    if factor is None:
        return degradation_rate(f.temp_mean_c, f.temp_max_c, f.maturity, k_lot, p)
    m_mat = lookup(p.maturity, f.maturity, "maturity")
    return p.k_ref * np.asarray(factor, dtype=float) * m_mat * np.asarray(k_lot)


def mean_quality(rate, hours):
    """Mean quality Q = exp(-k * hours), in (0, 1]."""
    h = np.asarray(hours, dtype=float)
    if np.any(h < 0):
        raise ValueError("hours must be >= 0")
    q = np.exp(-np.asarray(rate, dtype=float) * h)
    return np.clip(q, _EPS, 1.0)


def grade_fractions(q_mean, p: ProductParams) -> np.ndarray:
    """Fractions of fruit in grades A, B, C, D; array of shape (4, *shape(q_mean))."""
    q = np.clip(np.asarray(q_mean, dtype=float), _EPS, 1.0)
    below = [
        ndtr(np.log(th / q) / p.sigma_h) for th, _ in p.grades
    ]  # P(q_i < threshold)
    fa = 1.0 - below[0]
    fb = below[0] - below[1]
    fc = below[1] - below[2]
    fd = below[2]
    return np.stack([fa, fb, fc, fd])


def quality_to_grade(q_fruit: float, p: ProductParams) -> str:
    """Grade (A-D) of ONE fruit of quality ``q_fruit`` in (0, 1]."""
    if not 0 < q_fruit <= 1.0 + 1e-12:
        raise ValueError("fruit quality must be in (0, 1]")
    for (th, _), name in zip(p.grades, GRADE_NAMES, strict=False):
        if q_fruit >= th:
            return name
    return GRADE_NAMES[-1]


def value_fraction(q_mean, p: ProductParams):
    """Expected fraction of full value of a lot of mean quality ``q_mean`` (no damage)."""
    frac = grade_fractions(q_mean, p)
    mult = [m for _, m in p.grades] + [0.0]
    return sum(f * m for f, m in zip(frac, mult, strict=True))


def value_loss(q_mean, packaging, p: ProductParams):
    """Loss fraction in [0, 1]: 1 - value_fraction * (1 - packaging damage)."""
    damage = lookup(p.pack_damage, packaging, "packaging")
    loss = 1.0 - value_fraction(q_mean, p) * (1.0 - damage)
    return np.clip(loss, 0.0, 1.0)


def quality_and_loss(f, k_lot, p: ProductParams):
    """Mean quality and loss for ConditionFeatures ``f`` and lot multiplier ``k_lot``."""
    rate = degradation_rate_for_features(f, k_lot, p)
    q = mean_quality(rate, f.exposure_h)
    return q, apply_chilling_penalty(value_loss(q, f.packaging, p), f, p)
