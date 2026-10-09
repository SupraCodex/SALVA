"""Explicit and testable recommendation-policy parameters."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

Confidence = Literal["high", "medium", "low", "none"]
DEFAULT_ASSUMPTIONS = (
    "MODEL_BASED_ESTIMATE_NOT_GUARANTEE",
    "PRODUCT_PARAMETERS_REQUIRE_CALIBRATION",
    "MARKET_ABSORPTION_IS_AN_ASSUMPTION",
)


@dataclass(frozen=True)
class Policy:
    """Decision thresholds; none of these values alter simulation outputs.

    ``lam`` applies the downside-risk score ``P50 - lam * (P50 - P10)``.
    ``reference_value_fcfa`` should be the lot's gross reference value when known; if
    omitted, materiality is measured relative to the leading decision score.
    """

    lam: float = 0.5
    materiality: float = 0.03
    high_probability: float = 0.60
    medium_probability: float = 0.40
    clear_probability: float = 0.40
    high_gap_fraction: float = 0.10
    reference_value_fcfa: float | None = None
    high_temp_c: float = 30.0
    delay_hours: float = 6.0
    saturation_fraction: float = 0.10
    storage_binding_tolerance: float = 0.001
    long_detour_threshold_h: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "lam",
            "materiality",
            "high_probability",
            "medium_probability",
            "clear_probability",
            "high_gap_fraction",
            "saturation_fraction",
            "storage_binding_tolerance",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if self.medium_probability > self.high_probability:
            raise ValueError("medium_probability cannot exceed high_probability")
        for name in ("high_temp_c", "delay_hours"):
            if not isfinite(float(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        if self.reference_value_fcfa is not None and (
            not isfinite(float(self.reference_value_fcfa))
            or self.reference_value_fcfa <= 0
        ):
            raise ValueError(
                "reference_value_fcfa must be finite and > 0 when provided"
            )
        if self.long_detour_threshold_h is not None and (
            not isfinite(float(self.long_detour_threshold_h))
            or self.long_detour_threshold_h < 0
        ):
            raise ValueError(
                "long_detour_threshold_h must be finite and >= 0 when provided"
            )


@dataclass(frozen=True)
class Recommendation:
    """Machine-readable recommendation; explanatory prose belongs to the API/UI layer."""

    best_id: str | None
    confidence: Confidence
    rationale_codes: tuple[str, ...]
    ranked_ids: tuple[str, ...]
    scores_fcfa: tuple[tuple[str, float], ...]
    prob_best: float
    gap_fraction: float | None
    no_clear_winner: bool
    assumptions: tuple[str, ...] = DEFAULT_ASSUMPTIONS

    @property
    def best_option_id(self) -> str | None:
        """Readable alias; ``best_id`` is retained for the P3 adapter contract."""
        return self.best_id

    def as_dict(self) -> dict[str, object]:
        """Serialize stable decision fields, including the assumptions for RM-6."""
        return {
            "best_id": self.best_id,
            "confidence": self.confidence,
            "rationale_codes": list(self.rationale_codes),
            "ranked_ids": list(self.ranked_ids),
            "scores_fcfa": dict(self.scores_fcfa),
            "prob_best": self.prob_best,
            "gap_fraction": self.gap_fraction,
            "no_clear_winner": self.no_clear_winner,
            "assumptions": list(self.assumptions),
        }
