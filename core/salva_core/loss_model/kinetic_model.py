"""Kinetic loss model: the scientific reference and the production fallback."""

from __future__ import annotations

import numpy as np
from scipy.special import ndtri

from .. import kinetics
from ..contracts import ConditionFeatures, LossDistribution
from ..features import n_rows
from ..params import ProductParams

_U_EPS = 1e-9


def _py(x):
    return float(x) if np.ndim(x) == 0 else x


class KineticLossModel:
    """Implements the LossModel contract with the kinetic equations of kinetics.py.

    Lot-to-lot variability enters through k_lot = exp(sigma_lot * ndtri(u)), u ~ U(0,1).
    Because the loss is non-decreasing in k_lot, hence in u, the loss quantile of level
    ``q`` at fixed conditions is EXACTLY ``sample_loss(f, q)``: P10/P50/P90 are the
    losses at u = 0.1 / 0.5 / 0.9.  The three quantiles therefore come from one
    distribution and can never cross.
    """

    def __init__(self, params: ProductParams, version: str | None = None) -> None:
        """Create a kinetic model bound to one validated product parameter set."""
        self.params = params
        self.version = version or f"kinetic-1.0.0+{params.file_sha256[:8]}"

    def lot_multiplier(self, u):
        """Map uniform draws to the lognormal lot-level decay multiplier."""
        uu = np.clip(np.asarray(u, dtype=float), _U_EPS, 1.0 - _U_EPS)
        return np.exp(self.params.sigma_lot * ndtri(uu))

    def sample_loss(self, f: ConditionFeatures, u) -> np.ndarray:
        """Return loss fractions for the supplied conditions and uniform draws."""
        _, loss = kinetics.quality_and_loss(f, self.lot_multiplier(u), self.params)
        return np.asarray(loss)

    def mean_quality(self, f: ConditionFeatures, u=0.5) -> np.ndarray:
        """Return mean quality for one or more lot-variability quantiles."""
        q, _ = kinetics.quality_and_loss(f, self.lot_multiplier(u), self.params)
        return np.asarray(q)

    def predict(
        self, f: ConditionFeatures, *, with_factors: bool = False
    ) -> LossDistribution:
        """Return the P10, P50 and P90 loss distribution for the conditions."""
        p10, p50, p90 = (_py(self.sample_loss(f, q)) for q in (0.10, 0.50, 0.90))
        factors = None
        if with_factors and n_rows(f) == 1:
            from .factors import explain

            factors = explain(self, f, self.params)
        return LossDistribution(p10=p10, p50=p50, p90=p90, top_factors=factors)

    def remaining_shelf_life_p50_h(self, f: ConditionFeatures) -> np.ndarray:
        """Estimate hours until the configured P50 commercial-loss threshold.

        The estimate uses the P50 lot multiplier and holds the current effective
        temperature, maturity and packaging constant.  It is therefore a model
        estimate, not a field-validated expiry guarantee.  The threshold is stored in
        ``ProductParams`` so the backend can display its provenance.
        """
        if any(
            np.ndim(getattr(f, name)) != 0
            for name in ("temp_mean_c", "temp_max_c", "age_h")
        ):
            raise ValueError("remaining_shelf_life_p50_h requires one feature row")
        q_now = float(
            kinetics.mean_quality(
                kinetics.degradation_rate(
                    f.temp_mean_c,
                    f.temp_max_c,
                    f.maturity,
                    self.lot_multiplier(0.5),
                    self.params,
                ),
                f.age_h,
            )
        )
        current_loss = float(kinetics.value_loss(q_now, f.packaging, self.params))
        lo, hi = 1e-12, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2.0
            if (
                float(kinetics.value_loss(mid, f.packaging, self.params))
                > self.params.shelf_life_loss_threshold
            ):
                lo = mid
            else:
                hi = mid
        target_quality = hi
        rate = float(
            kinetics.degradation_rate(
                f.temp_mean_c,
                f.temp_max_c,
                f.maturity,
                self.lot_multiplier(0.5),
                self.params,
            )
        )
        if current_loss >= self.params.shelf_life_loss_threshold:
            return np.asarray(0.0)
        return np.asarray(max(0.0, np.log(q_now / target_quality) / max(rate, 1e-12)))
