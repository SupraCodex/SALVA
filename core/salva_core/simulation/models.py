"""Typed results shared by the pure simulation and allocation engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class AllocationLine:
    """Physical quantity routed through one candidate option.

    ``full_price_kg`` and ``surplus_kg`` are the LP's planning split, expressed in
    physical kg. Market saturation is re-evaluated under each Monte Carlo draw.
    """

    option_id: str
    full_price_kg: float
    surplus_kg: float

    @property
    def kg(self) -> float:
        """Return the total physical quantity assigned to this option."""
        return self.full_price_kg + self.surplus_kg


@dataclass(frozen=True)
class AllocationPlan:
    """Mass-conserving result of the linear allocation problem."""

    lines: tuple[AllocationLine, ...]
    discarded_kg: float
    objective_fcfa: float

    @property
    def allocated_kg(self) -> float:
        """Return the physical quantity assigned to routes, excluding discard."""
        return sum(line.kg for line in self.lines)

    @property
    def total_kg(self) -> float:
        """Return the conserved physical mass represented by the plan."""
        return self.allocated_kg + self.discarded_kg

    def as_dict(self) -> dict[str, Any]:
        """Serialize the plan without exposing solver-specific arrays."""
        return {
            "lines": [
                {
                    "option_id": line.option_id,
                    "kg": line.kg,
                    "full_price_kg": line.full_price_kg,
                    "surplus_kg": line.surplus_kg,
                }
                for line in self.lines
            ],
            "allocated_kg": self.allocated_kg,
            "discarded_kg": self.discarded_kg,
            "total_kg": self.total_kg,
            "objective_fcfa": self.objective_fcfa,
        }


@dataclass(frozen=True)
class ScenarioResult:
    """Monte Carlo summary for one candidate action or an optimized split.

    The ``*_draws`` arrays are retained for deterministic recommendation comparisons,
    but omitted from :meth:`as_dict` to keep API payloads small and JSON-safe.
    """

    id: str
    action: str
    feasible: bool
    loss_p10: float | None
    loss_p50: float | None
    loss_p90: float | None
    recoverable_kg_p10: float | None
    recoverable_kg_p50: float | None
    recoverable_kg_p90: float | None
    gross_value_p10: float | None
    gross_value_p50: float | None
    gross_value_p90: float | None
    net_p10: float | None
    net_p50: float | None
    net_p90: float | None
    prob_best: float = 0.0
    risk_level: str | None = None
    discouraged: bool = False
    discouraged_reason: str | None = None
    infeasible_reason: str | None = None
    allocation: AllocationPlan | None = None
    net_draws: np.ndarray = field(
        default_factory=lambda: np.empty(0), repr=False, compare=False
    )
    loss_draws: np.ndarray = field(
        default_factory=lambda: np.empty(0), repr=False, compare=False
    )
    recoverable_draws: np.ndarray = field(
        default_factory=lambda: np.empty(0), repr=False, compare=False
    )
    gross_draws: np.ndarray = field(
        default_factory=lambda: np.empty(0), repr=False, compare=False
    )
    surplus_fraction_p50: float = 0.0
    storage_used_kg: float = 0.0
    storage_capacity_kg: float = 0.0
    temp_mean_c: float | None = None
    temp_max_c: float | None = None
    delay_h: float = 0.0
    extra_h: float = 0.0
    cost_p50: float = 0.0

    @property
    def net_value_p10(self) -> float | None:
        """Return the P10 net value under the stable public spelling."""
        return self.net_p10

    @property
    def net_value_p50(self) -> float | None:
        """Return the P50 net value under the stable public spelling."""
        return self.net_p50

    @property
    def net_value_p90(self) -> float | None:
        """Return the P90 net value under the stable public spelling."""
        return self.net_p90

    @property
    def recoverable_kg_p50_value(self) -> float | None:
        """Compatibility-friendly spelling for serializers with explicit units."""
        return self.recoverable_kg_p50

    def as_dict(self) -> dict[str, Any]:
        """Return finite, JSON-serializable public fields (never the Monte Carlo vectors)."""
        out: dict[str, Any] = {
            "id": self.id,
            "action": self.action,
            "feasible": self.feasible,
            "discouraged": self.discouraged,
            "discouraged_reason": self.discouraged_reason,
            "infeasible_reason": self.infeasible_reason,
            "loss": {"p10": self.loss_p10, "p50": self.loss_p50, "p90": self.loss_p90},
            "recoverable_kg": {
                "p10": self.recoverable_kg_p10,
                "p50": self.recoverable_kg_p50,
                "p90": self.recoverable_kg_p90,
            },
            "gross_value_fcfa": {
                "p10": self.gross_value_p10,
                "p50": self.gross_value_p50,
                "p90": self.gross_value_p90,
            },
            "net_value_fcfa": {
                "p10": self.net_p10,
                "p50": self.net_p50,
                "p90": self.net_p90,
            },
            "prob_best": self.prob_best,
            "risk_level": self.risk_level,
            "surplus_fraction_p50": self.surplus_fraction_p50,
            "storage_used_kg": self.storage_used_kg,
            "storage_capacity_kg": self.storage_capacity_kg,
            "temp_mean_c": self.temp_mean_c,
            "temp_max_c": self.temp_max_c,
            "delay_h": self.delay_h,
            "extra_h": self.extra_h,
            "cost_p50_fcfa": self.cost_p50,
        }
        if self.allocation is not None:
            out["allocation"] = self.allocation.as_dict()
        return out
