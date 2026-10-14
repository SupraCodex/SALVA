"""Deterministic product-risk classification for the SALVA core.

Risk is not inferred from an arbitrary global constant.  Each product supplies four
versioned thresholds: two for median loss and two for predictive-interval width.  The
classification is conservative: a scenario is assigned the highest level implied by
either its P50 loss or its uncertainty width.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .contracts import LossDistribution
from .params import ProductParams

RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class RiskAssessment:
    """Machine-readable risk result with the exact values used for classification."""

    level: RiskLevel
    loss_p50: float
    interval_width: float
    loss_reason: str
    uncertainty_reason: str

    def as_dict(self) -> dict[str, float | str]:
        """Serialize the assessment for a backend response or audit record."""
        return {
            "level": self.level,
            "loss_p50": self.loss_p50,
            "interval_width": self.interval_width,
            "loss_reason": self.loss_reason,
            "uncertainty_reason": self.uncertainty_reason,
        }


def classify_risk(
    distribution: LossDistribution, params: ProductParams
) -> RiskAssessment:
    """Classify one loss distribution using the product's configured thresholds.

    ``P50`` and ``P10/P90`` must be scalar values here.  Vectorized model predictions
    belong to the offline pipeline; accepting them in this decision API would create
    an ambiguous risk level.
    """
    try:
        p10 = float(distribution.p10)
        p50 = float(distribution.p50)
        p90 = float(distribution.p90)
    except (TypeError, ValueError) as exc:
        raise ValueError("risk classification requires scalar P10/P50/P90") from exc
    if not all(0.0 <= value <= 1.0 for value in (p10, p50, p90)):
        raise ValueError("loss quantiles must be in [0, 1]")
    if not p10 <= p50 <= p90:
        raise ValueError("loss quantiles must satisfy P10 <= P50 <= P90")
    width = p90 - p10
    thresholds = params.risk_thresholds
    if p50 < thresholds["low_p50_max"]:
        loss_level: RiskLevel = "low"
        loss_reason = "P50_BELOW_LOW_THRESHOLD"
    elif p50 < thresholds["medium_p50_max"]:
        loss_level = "medium"
        loss_reason = "P50_BELOW_MEDIUM_THRESHOLD"
    else:
        loss_level = "high"
        loss_reason = "P50_AT_OR_ABOVE_HIGH_THRESHOLD"
    if width <= thresholds["low_width_max"]:
        uncertainty_level: RiskLevel = "low"
        uncertainty_reason = "INTERVAL_WIDTH_WITHIN_LOW_THRESHOLD"
    elif width <= thresholds["medium_width_max"]:
        uncertainty_level = "medium"
        uncertainty_reason = "INTERVAL_WIDTH_WITHIN_MEDIUM_THRESHOLD"
    else:
        uncertainty_level = "high"
        uncertainty_reason = "INTERVAL_WIDTH_ABOVE_MEDIUM_THRESHOLD"
    rank = {"low": 0, "medium": 1, "high": 2}
    level = max((loss_level, uncertainty_level), key=rank.__getitem__)
    return RiskAssessment(level, p50, width, loss_reason, uncertainty_reason)
