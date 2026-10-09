"""Optional temperature/delay sensitivity analysis built on the production engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np

from ..contracts import Lot, Option
from ..params import ProductParams
from .engine import run_all
from .uncertainty import draw

if TYPE_CHECKING:
    from ..recommendation import Policy


@dataclass(frozen=True)
class SensitivityPoint:
    """Recommendation at one temperature and delay combination."""

    temp_c: float
    delay_h: float
    best_id: str | None
    confidence: str
    risk_levels: dict[str, str | None]


@dataclass(frozen=True)
class SensitivityTransition:
    """Adjacent grid cells where the recommended action changes."""

    from_temp_c: float
    from_delay_h: float
    to_temp_c: float
    to_delay_h: float
    from_best_id: str | None
    to_best_id: str | None


@dataclass(frozen=True)
class SensitivityResult:
    """Complete sensitivity grid and its detected decision boundaries."""

    temperatures_c: tuple[float, ...]
    delays_h: tuple[float, ...]
    points: tuple[SensitivityPoint, ...]
    transitions: tuple[SensitivityTransition, ...]

    def at(self, temp_c: float, delay_h: float) -> SensitivityPoint:
        """Return the exact grid point identified by temperature and delay."""
        for point in self.points:
            if point.temp_c == temp_c and point.delay_h == delay_h:
                return point
        raise KeyError((temp_c, delay_h))


def analyze_sensitivity(
    model,
    lot: Lot,
    options: Sequence[Option],
    params: ProductParams,
    temperatures_c: Sequence[float],
    delays_h: Sequence[float],
    *,
    n_draws: int = 1_000,
    seed: int = 42,
    policy: Policy | None = None,
) -> SensitivityResult:
    """Evaluate best actions on a temperature/delay grid with common random numbers.

    Delay is interpreted as the current delay against the same planned transit: the
    planned transit is ``lot.remaining_h - lot.delay_h`` and each grid delay is added
    to it.  Every cell uses the same seeded shock bundle, making boundaries comparable.
    """
    temps = _grid_values(temperatures_c, "temperatures_c")
    delays = _grid_values(delays_h, "delays_h")
    if n_draws < 1_000:
        raise ValueError("sensitivity requires at least 1000 Monte Carlo draws")
    planned_h = lot.remaining_h - lot.delay_h
    if planned_h < 0:
        raise ValueError("lot.remaining_h must include a delay no greater than itself")
    shocks = draw(n_draws, seed)
    points: list[SensitivityPoint] = []
    lookup: dict[tuple[float, float], SensitivityPoint] = {}
    from ..recommendation import Policy, recommend

    policy = policy or Policy()
    for temp_c in temps:
        for delay_h in delays:
            cell_lot = replace(
                lot,
                temp_c=temp_c,
                delay_h=delay_h,
                remaining_h=planned_h + delay_h,
            )
            results = run_all(model, cell_lot, options, shocks, params)
            recommendation = recommend(results, policy)
            point = SensitivityPoint(
                temp_c=temp_c,
                delay_h=delay_h,
                best_id=recommendation.best_id,
                confidence=recommendation.confidence,
                risk_levels={result.id: result.risk_level for result in results},
            )
            points.append(point)
            lookup[(temp_c, delay_h)] = point
    transitions: list[SensitivityTransition] = []
    for temp_c in temps:
        for left, right in pairwise(delays):
            _append_transition(
                transitions, lookup[(temp_c, left)], lookup[(temp_c, right)]
            )
    for delay_h in delays:
        for top, bottom in pairwise(temps):
            _append_transition(
                transitions, lookup[(top, delay_h)], lookup[(bottom, delay_h)]
            )
    return SensitivityResult(temps, delays, tuple(points), tuple(transitions))


def _grid_values(values: Sequence[float], field: str) -> tuple[float, ...]:
    """Validate and normalize one sensitivity axis."""
    result = tuple(sorted(float(value) for value in values))
    if not result or len(set(result)) != len(result):
        raise ValueError(f"{field} must contain at least one distinct value")
    if not all(np.isfinite(value) for value in result):
        raise ValueError(f"{field} must contain only finite values")
    if field == "delays_h" and any(value < 0 for value in result):
        raise ValueError("delays_h must be >= 0")
    return result


def _append_transition(
    out: list[SensitivityTransition], before: SensitivityPoint, after: SensitivityPoint
) -> None:
    """Record a boundary only when the selected action changes."""
    if before.best_id != after.best_id:
        out.append(
            SensitivityTransition(
                before.temp_c,
                before.delay_h,
                after.temp_c,
                after.delay_h,
                before.best_id,
                after.best_id,
            )
        )
