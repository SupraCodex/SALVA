"""Kinetic loss model: the scientific reference and the production fallback."""

from __future__ import annotations

import numpy as np
from scipy.special import ndtri

from .. import kinetics
from ..contracts import ConditionFeatures, LossDistribution
from ..features import n_rows, out_of_range_features, out_of_range_mask
from ..params import ProductParams, lookup

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
        self.version = version or f"kinetic-2.0.0+{params.file_sha256[:8]}"

    def lot_multiplier(self, u):
        """Map uniform draws to the lognormal lot-level decay multiplier."""
        uu = np.clip(np.asarray(u, dtype=float), _U_EPS, 1.0 - _U_EPS)
        return np.exp(self.params.sigma_lot * ndtri(uu))

    def sample_loss(self, f: ConditionFeatures, u) -> np.ndarray:
        """Return loss fractions for the supplied conditions and uniform draws."""
        loss = self._raw_sample_loss(f, u)
        outside = out_of_range_mask(f, self.params)
        if not np.any(outside):
            return loss

        scalar = loss.ndim == 0
        values = loss.reshape(1) if scalar else loss
        uniforms = np.broadcast_to(np.asarray(u, dtype=float), values.shape)
        median_loss = self._raw_sample_loss(f, 0.5)
        medians = (
            np.full(values.shape, float(median_loss))
            if median_loss.ndim == 0
            else np.broadcast_to(median_loss, values.shape)
        )
        outside = np.broadcast_to(outside, values.shape)
        lower = medians * np.clip((uniforms - 0.1) / 0.4, 0.0, 1.0)
        upper = medians + (1.0 - medians) * np.clip((uniforms - 0.5) / 0.4, 0.0, 1.0)
        widened = np.where(uniforms <= 0.5, lower, upper)
        result = np.where(outside, widened, values)
        return result.reshape(()) if scalar else result

    def _raw_sample_loss(self, f: ConditionFeatures, u) -> np.ndarray:
        """Evaluate the unexpanded kinetic quantile function."""
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
        return LossDistribution(
            p10=p10,
            p50=p50,
            p90=p90,
            top_factors=factors,
            extrapolated_features=out_of_range_features(f, self.params),
        )

    def remaining_shelf_life_p50_h(self, f: ConditionFeatures) -> np.ndarray | None:
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
        k_lot = self.lot_multiplier(0.5)
        maturity_factor = lookup(self.params.maturity, f.maturity, "maturity")
        historical_factor = f.historical_rate_factor
        if historical_factor is None:
            historical_factor = kinetics.thermal_factor(
                f.temp_mean_c, f.temp_max_c, self.params
            )
        q_now = float(
            kinetics.mean_quality(
                self.params.k_ref * historical_factor * maturity_factor * k_lot,
                f.age_h,
            )
        )
        historical_chill = float(
            kinetics.chilling_equivalent_exposure_h(f, self.params, phase="historical")
        )
        current_base_loss = float(kinetics.value_loss(q_now, f.packaging, self.params))
        current_chill = float(
            kinetics.chilling_loss_fraction_from_dose(
                historical_chill, f.maturity, self.params
            )
        )
        current_loss = 1.0 - (1.0 - current_base_loss) * (1.0 - current_chill)
        threshold = self.params.shelf_life_loss_threshold
        if current_loss >= threshold:
            return np.asarray(0.0)
        future_factor = f.future_rate_factor
        if future_factor is None:
            future_factor = kinetics.thermal_factor(
                f.temp_mean_c, f.temp_max_c, self.params
            )
        rate = float(self.params.k_ref * future_factor * maturity_factor * k_lot)
        future_hours = float(f.remaining_transit_h) + float(f.hold_h)
        future_chill = float(
            kinetics.chilling_equivalent_exposure_h(f, self.params, phase="future")
        )
        if future_hours > 0.0:
            chill_rate = future_chill / future_hours
        else:
            future_temp = (
                f.transit_temp_mean_c
                if f.transit_temp_mean_c is not None
                else f.temp_mean_c
            )
            threshold_c = float(
                lookup(self.params.chilling_threshold_c, f.maturity, "maturity")
            )
            below = max(threshold_c - float(future_temp), 0.0)
            chill_rate = (
                float(
                    np.exp(min(below / self.params.chilling_temperature_scale_c, 40.0))
                )
                if float(future_temp) < threshold_c
                else 0.0
            )

        def projected_loss(hours: float) -> float:
            projected_quality = float(q_now * np.exp(-rate * hours))
            base_loss = float(
                kinetics.value_loss(projected_quality, f.packaging, self.params)
            )
            dose = historical_chill + chill_rate * hours
            injury = float(
                kinetics.chilling_loss_fraction_from_dose(dose, f.maturity, self.params)
            )
            return 1.0 - (1.0 - base_loss) * (1.0 - injury)

        low, high = 0.0, 1.0
        while projected_loss(high) < threshold and high < 1e9:
            high *= 2.0
        if projected_loss(high) < threshold:
            return None
        for _ in range(80):
            mid = (low + high) / 2.0
            if projected_loss(mid) >= threshold:
                high = mid
            else:
                low = mid
        return np.asarray(high)
