"""Stable, non-generative reason codes for recommendation outputs."""

from __future__ import annotations

from typing import Sequence

from ..simulation.models import ScenarioResult
from .policy import Policy


def rationale_codes(
    results: Sequence[ScenarioResult],
    best: ScenarioResult | None,
    policy: Policy,
) -> tuple[str, ...]:
    """Return ordered codes grounded solely in model outputs and configured thresholds."""
    if best is None:
        if any(result.feasible for result in results):
            return ("ALL_OPTIONS_DISCOURAGED",)
        return ("NO_FEASIBLE_ACTION",)

    codes: list[str] = []
    if best.temp_max_c is not None and best.temp_max_c > policy.high_temp_c:
        codes.append("HIGH_TEMP")
    if best.delay_h >= policy.delay_hours:
        codes.append("DELAY")
    if best.surplus_fraction_p50 > policy.saturation_fraction:
        codes.append("MARKET_SATURATION_AT_DEST")
    if (
        best.storage_capacity_kg > 0
        and best.storage_used_kg >= best.storage_capacity_kg * (1.0 - policy.storage_binding_tolerance)
    ):
        codes.append("STORAGE_CAPACITY_BINDING")
    if (
        policy.long_detour_threshold_h is not None
        and best.action in {"reroute", "optimized_split"}
        and best.extra_h >= policy.long_detour_threshold_h
        and best.cost_p50 > 0
    ):
        codes.append("LONG_DETOUR_COST")
    if best.loss_p50 is not None and best.loss_p50 <= 0.10:
        codes.append("LOW_RISK_NO_URGENT_ACTION")

    eligible = [r for r in results if r.feasible and not r.discouraged]
    if len(eligible) == 1:
        codes.append("SINGLE_FEASIBLE_ACTION")
    if eligible and all(r.net_p50 is not None and r.net_p50 < 0 for r in eligible):
        codes.append("ALL_OPTIONS_NEGATIVE")
    return tuple(codes)
