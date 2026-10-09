"""Optional temperature/delay sensitivity analysis built on the production engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from math import isfinite
from typing import TYPE_CHECKING

import numpy as np

from ..contracts import Lot, Option
from ..params import ProductParams
from .engine import run_all
from .uncertainty import draw

if TYPE_CHECKING:
    from ..recommendation import Policy, Recommendation


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


@dataclass(frozen=True)
class ParameterSensitivityPoint:
    """Recommendation impact of a parameter scaled by minus/plus a percentage."""

    parameter: str
    baseline_value: float
    minus_value: float
    plus_value: float
    baseline: Recommendation
    minus: Recommendation
    plus: Recommendation

    @property
    def decision_changed_minus(self) -> bool:
        return self.minus.best_id != self.baseline.best_id

    @property
    def decision_changed_plus(self) -> bool:
        return self.plus.best_id != self.baseline.best_id

    def as_dict(self) -> dict[str, object]:
        """Serialize tested values, recommendations and decision-flip flags."""
        return {
            "parameter": self.parameter,
            "baseline_value": self.baseline_value,
            "minus_value": self.minus_value,
            "plus_value": self.plus_value,
            "baseline": self.baseline.as_dict(),
            "minus": self.minus.as_dict(),
            "plus": self.plus.as_dict(),
            "decision_changed_minus": self.decision_changed_minus,
            "decision_changed_plus": self.decision_changed_plus,
        }


@dataclass(frozen=True)
class ParameterSensitivityResult:
    """Parameter perturbation results evaluated under a shared shock bundle."""

    relative_change: float
    points: tuple[ParameterSensitivityPoint, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a backend-friendly summary of all tested parameter perturbations."""
        return {
            "relative_change": self.relative_change,
            "points": [point.as_dict() for point in self.points],
        }


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


def analyze_parameter_sensitivity(
    model,
    lot: Lot,
    options: Sequence[Option],
    params: ProductParams,
    shocks,
    parameters: Sequence[str],
    *,
    relative_change: float = 0.30,
    policy: Policy | None = None,
) -> ParameterSensitivityResult:
    """Re-run decisions after ±relative changes to explicit numeric assumptions.

    Supported paths are ``product.<scalar>``, ``product.<mapping>.<category>``,
    ``option:<option-id>.<numeric-field>`` and ``market:<market-id>.price`` or
    ``market:<market-id>.absorb_kg``. Each perturbation reuses exactly the supplied
    common shocks. Zero baselines are rejected because a relative percentage cannot
    measure the impact of an additive assumption at zero.
    """
    from ..recommendation import Policy, recommend

    if isinstance(relative_change, bool) or not isfinite(float(relative_change)):
        raise ValueError("relative_change must be finite and in (0, 1)")
    change = float(relative_change)
    if not 0.0 < change < 1.0:
        raise ValueError("relative_change must be finite and in (0, 1)")
    names = tuple(parameters)
    if not names or len(set(names)) != len(names):
        raise ValueError("parameters must contain at least one distinct path")
    if not options:
        raise ValueError("at least one option is required")

    chosen_policy = policy or Policy()
    baseline_model = (
        _model_for_params(model, params, "product.baseline")
        if any(name.startswith("product.") for name in names)
        else model
    )
    baseline_rec = recommend(
        run_all(baseline_model, lot, options, shocks, params), chosen_policy
    )
    points: list[ParameterSensitivityPoint] = []
    for name in names:
        base, _, _ = _parameter_variants(name, options, params)
        minus_value = base * (1.0 - change)
        plus_value = base * (1.0 + change)
        minus_params, minus_options = _apply_parameter(
            name, minus_value, options, params
        )
        plus_params, plus_options = _apply_parameter(name, plus_value, options, params)
        minus_model = _model_for_params(model, minus_params, name)
        plus_model = _model_for_params(model, plus_params, name)
        minus_rec = recommend(
            run_all(minus_model, lot, minus_options, shocks, minus_params),
            chosen_policy,
        )
        plus_rec = recommend(
            run_all(plus_model, lot, plus_options, shocks, plus_params), chosen_policy
        )
        points.append(
            ParameterSensitivityPoint(
                name,
                base,
                minus_value,
                plus_value,
                baseline_rec,
                minus_rec,
                plus_rec,
            )
        )
    return ParameterSensitivityResult(change, tuple(points))


_PRODUCT_SCALARS = frozenset(
    {
        "k_ref",
        "q10",
        "sigma_h",
        "sigma_lot",
        "delta",
        "default_diurnal_amp_c",
        "shelf_life_loss_threshold",
        "chilling_temperature_scale_c",
        "chilling_loss_rate_per_equivalent_h",
    }
)
_PRODUCT_MAPPINGS = frozenset(
    {
        "maturity",
        "pack_delta_c",
        "pack_damage",
        "storage_temp_offset_c",
        "chilling_threshold_c",
        "chilling_onset_equivalent_h",
    }
)
_OPTION_FIELDS = frozenset(
    {
        "kg",
        "extra_h",
        "hold_h",
        "temp_offset",
        "cost",
        "storage_cost_fcfa_kg_day",
        "transport_distance_km",
        "transport_cost_fcfa_kg_km",
    }
)


def _parameter_variants(
    path: str, options: Sequence[Option], params: ProductParams
) -> tuple[float, ProductParams, list[Option]]:
    """Resolve the numeric baseline and validate that the requested path is supported."""
    if path.startswith("product."):
        fields = path.split(".")
        if len(fields) == 2 and fields[1] in _PRODUCT_SCALARS:
            value = getattr(params, fields[1])
        elif (
            len(fields) == 3
            and fields[1] in _PRODUCT_MAPPINGS
            and fields[2] in getattr(params, fields[1])
        ):
            value = getattr(params, fields[1])[fields[2]]
        else:
            raise ValueError(f"unsupported product sensitivity path {path!r}")
    elif path.startswith("option:"):
        target, separator, field_name = path[len("option:") :].rpartition(".")
        matches = [option for option in options if option.id == target]
        if not separator or field_name not in _OPTION_FIELDS or len(matches) != 1:
            raise ValueError(f"unsupported option sensitivity path {path!r}")
        value = getattr(matches[0], field_name)
    elif path.startswith("market:"):
        target, separator, field_name = path[len("market:") :].rpartition(".")
        try:
            market_id = int(target)
        except ValueError as exc:
            raise ValueError(
                f"market sensitivity id must be an integer in {path!r}"
            ) from exc
        if not separator or field_name not in {"price", "absorb_kg"}:
            raise ValueError(f"unsupported market sensitivity path {path!r}")
        matches = [option for option in options if option.market.id == market_id]
        if not matches:
            raise ValueError(f"market {market_id} is not present in the options")
        metadata = {
            (option.market.price, option.market.absorb_kg) for option in matches
        }
        if len(metadata) != 1:
            raise ValueError(f"market {market_id} has inconsistent input metadata")
        value = getattr(matches[0].market, field_name)
    else:
        raise ValueError("parameter paths must start with product., option: or market:")
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{path}: sensitivity requires a non-zero numeric baseline")
    try:
        base = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{path}: sensitivity requires a numeric baseline") from exc
    if not isfinite(base) or base == 0.0:
        raise ValueError(f"{path}: sensitivity requires a finite, non-zero baseline")
    return base, params, list(options)


def _apply_parameter(
    path: str,
    value: float,
    options: Sequence[Option],
    params: ProductParams,
) -> tuple[ProductParams, list[Option]]:
    """Return immutable parameter/option copies with one supported value changed."""
    if path.startswith("product."):
        fields = path.split(".")
        if len(fields) == 2:
            scalar = fields[1]
            if scalar == "k_ref":
                params = replace(params, k_ref=value)
            elif scalar == "q10":
                params = replace(params, q10=value)
            elif scalar == "sigma_h":
                params = replace(params, sigma_h=value)
            elif scalar == "sigma_lot":
                params = replace(params, sigma_lot=value)
            elif scalar == "delta":
                params = replace(params, delta=value)
            elif scalar == "default_diurnal_amp_c":
                params = replace(params, default_diurnal_amp_c=value)
            elif scalar == "shelf_life_loss_threshold":
                params = replace(params, shelf_life_loss_threshold=value)
            elif scalar == "chilling_temperature_scale_c":
                params = replace(params, chilling_temperature_scale_c=value)
            elif scalar == "chilling_loss_rate_per_equivalent_h":
                params = replace(params, chilling_loss_rate_per_equivalent_h=value)
            else:
                raise ValueError(f"unsupported product sensitivity path {path!r}")
        else:
            mapping = dict(getattr(params, fields[1]))
            mapping[fields[2]] = value
            if fields[1] == "maturity":
                params = replace(params, maturity=mapping)
            elif fields[1] == "pack_delta_c":
                params = replace(params, pack_delta_c=mapping)
            elif fields[1] == "pack_damage":
                params = replace(params, pack_damage=mapping)
            elif fields[1] == "storage_temp_offset_c":
                params = replace(params, storage_temp_offset_c=mapping)
            elif fields[1] == "chilling_threshold_c":
                params = replace(params, chilling_threshold_c=mapping)
            elif fields[1] == "chilling_onset_equivalent_h":
                params = replace(params, chilling_onset_equivalent_h=mapping)
            else:
                raise ValueError(f"unsupported product sensitivity path {path!r}")
        _validate_product_perturbation(path, value)
        return params, list(options)
    varied: list[Option] = []
    if path.startswith("option:"):
        target, _, field_name = path[len("option:") :].rpartition(".")
        for option in options:
            if option.id != target:
                varied.append(option)
            elif field_name == "kg":
                varied.append(replace(option, kg=value))
            elif field_name == "extra_h":
                varied.append(replace(option, extra_h=value))
            elif field_name == "hold_h":
                varied.append(replace(option, hold_h=value))
            elif field_name == "temp_offset":
                varied.append(replace(option, temp_offset=value))
            elif field_name == "cost":
                varied.append(replace(option, cost=value))
            elif field_name == "storage_cost_fcfa_kg_day":
                varied.append(replace(option, storage_cost_fcfa_kg_day=value))
            elif field_name == "transport_distance_km":
                varied.append(replace(option, transport_distance_km=value))
            elif field_name == "transport_cost_fcfa_kg_km":
                varied.append(replace(option, transport_cost_fcfa_kg_km=value))
            else:
                raise ValueError(f"unsupported option sensitivity path {path!r}")
        return params, varied
    target, _, field_name = path[len("market:") :].rpartition(".")
    market_id = int(target)
    for option in options:
        if option.market.id != market_id:
            varied.append(option)
            continue
        if field_name == "price":
            market = replace(option.market, price=value)
        elif field_name == "absorb_kg":
            market = replace(option.market, absorb_kg=value)
        else:
            raise ValueError(f"unsupported market sensitivity path {path!r}")
        varied.append(replace(option, market=market))
    return params, varied


def _model_for_params(model, params: ProductParams, path: str):
    """Rebind product-sensitive models; never report a perturbation the model ignored."""
    if not path.startswith("product."):
        return model
    binder = getattr(model, "with_params", None)
    if not callable(binder):
        raise TypeError(
            f"model {type(model).__name__} cannot rebind ProductParams for {path!r}"
        )
    varied_model = binder(params)
    if varied_model is model or getattr(varied_model, "params", None) is not params:
        raise TypeError("LossModel.with_params must return a model bound to new params")
    return varied_model


def _validate_product_perturbation(path: str, value: float) -> None:
    """Keep ± percentage scenarios inside the product parameter's physical domain."""
    field = path.split(".")[1]
    if field == "q10" and value < 1.0:
        raise ValueError(f"{path}: perturbed q10 must be >= 1")
    if field in {"k_ref", "sigma_h", "chilling_temperature_scale_c"} and value <= 0:
        raise ValueError(f"{path}: perturbed value must be > 0")
    if (
        field
        in {"sigma_lot", "default_diurnal_amp_c", "chilling_loss_rate_per_equivalent_h"}
        and value < 0
    ):
        raise ValueError(f"{path}: perturbed value must be >= 0")
    if field == "delta" and not 0.0 <= value <= 1.0:
        raise ValueError(f"{path}: perturbed delta must be in [0, 1]")
    if field == "shelf_life_loss_threshold" and not 0.0 < value < 1.0:
        raise ValueError(f"{path}: perturbed threshold must be in (0, 1)")
    if len(path.split(".")) == 3:
        mapping = path.split(".")[1]
        if mapping == "maturity" and value <= 0:
            raise ValueError(f"{path}: perturbed maturity multiplier must be > 0")
        if mapping == "pack_damage" and not 0.0 <= value < 1.0:
            raise ValueError(f"{path}: perturbed pack damage must be in [0, 1)")
        if mapping == "chilling_threshold_c" and not 0.0 <= value <= 50.0:
            raise ValueError(f"{path}: perturbed chilling threshold must be in [0, 50]")
        if mapping == "chilling_onset_equivalent_h" and value <= 0:
            raise ValueError(f"{path}: perturbed chilling onset must be > 0")


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
