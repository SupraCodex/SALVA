"""Single source of truth for feature construction.

Used by BOTH offline data generation (ml/generate.py) and production (simulation
engine of P1, backend of P2): the model can never be trained on a different feature
logic than the one used at inference (no training-serving skew).

    assemble(...)  array-capable core routine (floats or NumPy arrays)
    build(lot, option, shocks, p)   the entry point P1 calls inside the simulation
    with_changes(f, p, **changes)   counterfactual copies (explanations, monotonicity)
    to_matrix(f) / from_arrays(...) numeric encoding shared by training and inference
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import numpy as np
from scipy.special import i0

from .contracts import ConditionFeatures, Lot, Option, Shocks
from .params import ParamsError, ProductParams, lookup

FEATURE_VERSION = "2.0.0"
NUMERIC_FEATURES = (
    "age_h",
    "temp_mean_c",
    "temp_max_c",
    "degree_hours_above_ref",
    "remaining_transit_h",
    "delay_h",
    "hold_h",
    "exposure_h",
)
CATEGORICAL_FEATURES = ("maturity", "packaging", "storage_mode")
MODEL_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Integer codes used for model inputs. Changing them requires bumping FEATURE_VERSION.
MATURITY_CODES = {"green": 0, "breaker": 1, "ripe": 2}
PACKAGING_CODES = {"crate": 0, "carton": 1, "sack": 2}
STORAGE_CODES = {"none": 0, "ambient_shade": 1, "ventilated": 2, "cold_room": 3}
CODE_MAPS = {
    "maturity": MATURITY_CODES,
    "packaging": PACKAGING_CODES,
    "storage_mode": STORAGE_CODES,
}

# Monotone relationship with the loss (+1: loss never decreases when the feature grows).
MONOTONE_INCREASING = (
    "age_h",
    "temp_mean_c",
    "temp_max_c",
    "degree_hours_above_ref",
    "remaining_transit_h",
    "delay_h",
    "hold_h",
    "exposure_h",
    "maturity",
)


def feature_schema() -> dict[str, Any]:
    """Return the versioned feature schema consumed by training and inference."""
    return {
        "version": FEATURE_VERSION,
        "columns": list(MODEL_COLUMNS),
        "numeric": list(NUMERIC_FEATURES),
        "categorical": list(CATEGORICAL_FEATURES),
        "codes": {k: dict(v) for k, v in CODE_MAPS.items()},
        "monotone_increasing": list(MONOTONE_INCREASING),
    }


def schema_hash() -> str:
    """Return the SHA-256 fingerprint of the exact feature schema."""
    blob = json.dumps(feature_schema(), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def check_params_compatible(p: ProductParams) -> None:
    """The YAML may only use categories known to the feature schema."""
    for key, mapping, codes in (
        ("maturity", p.maturity, MATURITY_CODES),
        ("pack_delta_c", p.pack_delta_c, PACKAGING_CODES),
        ("pack_damage", p.pack_damage, PACKAGING_CODES),
        ("storage_temp_offset_c", p.storage_temp_offset_c, STORAGE_CODES),
    ):
        extra = set(mapping) - set(codes)
        if extra:
            raise ParamsError(
                f"{p.name}.{key}: categories {sorted(extra)} unknown to features.py"
            )


def _arr(x: Any, name: str) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} contains NaN or infinity")
    return a


def _nonneg(a: np.ndarray, name: str) -> np.ndarray:
    if np.any(a < 0):
        raise ValueError(f"{name} must be >= 0")
    return a


def _unwrap(x: np.ndarray) -> float | np.ndarray:
    return float(x) if x.ndim == 0 else x


def _phase_statistics(
    p: ProductParams,
    history_temp: np.ndarray,
    transit_temp: np.ndarray,
    storage_temp: np.ndarray,
    age: np.ndarray,
    transit_h: np.ndarray,
    hold_h: np.ndarray,
    diurnal_amp: np.ndarray,
) -> dict[str, np.ndarray]:
    """Summarize physical phases while retaining their exact Q10 dose."""
    (
        history_temp,
        transit_temp,
        storage_temp,
        age,
        transit_h,
        hold_h,
        diurnal_amp,
    ) = np.broadcast_arrays(
        history_temp,
        transit_temp,
        storage_temp,
        age,
        transit_h,
        hold_h,
        diurnal_amp,
    )
    exposure = age + transit_h + hold_h
    safe_exposure = np.maximum(exposure, 1e-12)
    temp_mean = np.divide(
        age * history_temp + transit_h * transit_temp + hold_h * storage_temp,
        safe_exposure,
        out=np.asarray(transit_temp, dtype=float).copy(),
        where=exposure > 0,
    )
    history_factor = p.q10 ** ((history_temp - p.t_ref_c) / 10.0) * i0(
        diurnal_amp * np.log(p.q10) / 10.0
    )
    transit_factor = p.q10 ** ((transit_temp - p.t_ref_c) / 10.0) * i0(
        diurnal_amp * np.log(p.q10) / 10.0
    )
    # Storage temperature is controlled and stable; weather-driven daily variation
    # applies to the historical and transit phases, not to the storage hold.
    storage_factor = p.q10 ** ((storage_temp - p.t_ref_c) / 10.0)
    total_factor = np.where(
        exposure > 0,
        (age * history_factor + transit_h * transit_factor + hold_h * storage_factor)
        / safe_exposure,
        transit_factor,
    )
    future_h = transit_h + hold_h
    future_factor = np.where(
        future_h > 0,
        (transit_h * transit_factor + hold_h * storage_factor)
        / np.maximum(future_h, 1e-12),
        transit_factor,
    )
    temp_max = np.where(age > 0, history_temp + diurnal_amp, -np.inf)
    temp_max = np.where(
        transit_h > 0,
        np.maximum(temp_max, transit_temp + diurnal_amp),
        temp_max,
    )
    temp_max = np.where(hold_h > 0, np.maximum(temp_max, storage_temp), temp_max)
    temp_max = np.where(exposure > 0, temp_max, transit_temp + diurnal_amp)
    degree_hours = (
        np.maximum(history_temp - p.t_ref_c, 0.0) * age
        + np.maximum(transit_temp - p.t_ref_c, 0.0) * transit_h
        + np.maximum(storage_temp - p.t_ref_c, 0.0) * hold_h
    )
    return {
        "temp_mean_c": temp_mean,
        "temp_max_c": temp_max,
        "exposure_h": exposure,
        "degree_hours_above_ref": degree_hours,
        "thermal_rate_factor": total_factor,
        "historical_rate_factor": history_factor,
        "future_rate_factor": future_factor,
    }


def assemble(
    p: ProductParams,
    *,
    maturity: Any,
    packaging: Any,
    age_h: Any,
    remaining_h: Any,
    temp_air_c: Any,
    delay_h: Any = 0.0,
    diurnal_amp_c: Any = None,
    temp_shock_c: Any = 0.0,
    transit_factor: Any = 1.0,
    extra_h: Any = 0.0,
    hold_h: Any = 0.0,
    temp_offset_c: Any = 0.0,
    storage_mode: Any = "none",
    product: str | None = None,
) -> ConditionFeatures:
    """Build ConditionFeatures from raw conditions (floats or arrays, broadcast together).

    ``remaining_h`` is the hours to arrival INCLUDING the delay ``delay_h``.
    ``extra_h`` is additional transit/detour time and is scaled by ``transit_factor``.
    ``hold_h`` is a separate fixed storage duration; the storage temperature offset is
    applied only during that phase. Historical age uses unshocked reference conditions.
    """
    check_params_compatible(p)
    age = _nonneg(_arr(age_h, "age_h"), "age_h")
    rem = _nonneg(_arr(remaining_h, "remaining_h"), "remaining_h")
    extra = _nonneg(_arr(extra_h, "extra_h"), "extra_h")
    hold = _nonneg(_arr(hold_h, "hold_h"), "hold_h")
    delay = _nonneg(_arr(delay_h, "delay_h"), "delay_h")
    if np.any(delay > rem + 1e-9):
        raise ValueError("delay_h cannot exceed remaining_h (the delay is part of it)")
    factor = _arr(transit_factor, "transit_factor")
    if np.any(factor <= 0):
        raise ValueError("transit_factor must be > 0")
    air = _arr(temp_air_c, "temp_air_c")
    air_range = p.valid_ranges.get("temp_mean_c")
    if air_range and (np.any(air < air_range["min"]) or np.any(air > air_range["max"])):
        raise ValueError(
            f"temp_air_c must be within [{air_range['min']}, {air_range['max']}] degC"
        )
    amp = p.default_diurnal_amp_c if diurnal_amp_c is None else diurnal_amp_c
    amp = _nonneg(_arr(amp, "diurnal_amp_c"), "diurnal_amp_c")

    pack_delta = lookup(p.pack_delta_c, packaging, "packaging")
    history_temp = air + pack_delta
    transit_temp = history_temp + _arr(temp_shock_c, "temp_shock_c")
    storage_temp = transit_temp + _arr(temp_offset_c, "temp_offset_c")
    # A storage category without a positive hold is not an exposure and must not
    # influence a statistical model through the categorical storage feature.
    lookup(STORAGE_CODES_FLOAT, storage_mode, "storage_mode")
    active_storage_mode = np.where(np.asarray(hold) > 0, storage_mode, "none")
    storage_temp = np.where(np.asarray(hold) > 0, storage_temp, transit_temp)
    remaining_transit = (rem + extra) * factor
    stats = _phase_statistics(
        p, history_temp, transit_temp, storage_temp, age, remaining_transit, hold, amp
    )
    lookup(p.maturity, maturity, "maturity")  # validates categories
    return ConditionFeatures(
        product=product or p.name,
        maturity=maturity
        if isinstance(maturity, str)
        else np.asarray(maturity, dtype=object),
        packaging=packaging
        if isinstance(packaging, str)
        else np.asarray(packaging, dtype=object),
        storage_mode=(
            str(active_storage_mode)
            if np.ndim(active_storage_mode) == 0
            else np.asarray(active_storage_mode, dtype=object)
        ),
        age_h=_unwrap(age),
        temp_mean_c=_unwrap(stats["temp_mean_c"]),
        temp_max_c=_unwrap(stats["temp_max_c"]),
        degree_hours_above_ref=_unwrap(stats["degree_hours_above_ref"]),
        remaining_transit_h=_unwrap(remaining_transit),
        delay_h=_unwrap(delay),
        hold_h=_unwrap(hold),
        exposure_h=_unwrap(stats["exposure_h"]),
        thermal_rate_factor=_unwrap(stats["thermal_rate_factor"]),
        historical_rate_factor=_unwrap(stats["historical_rate_factor"]),
        future_rate_factor=_unwrap(stats["future_rate_factor"]),
        history_temp_mean_c=_unwrap(history_temp),
        transit_temp_mean_c=_unwrap(transit_temp),
        storage_temp_mean_c=_unwrap(storage_temp),
        diurnal_amp_c=_unwrap(amp),
    )


STORAGE_CODES_FLOAT = {k: float(v) for k, v in STORAGE_CODES.items()}


def option_durations(opt: Option) -> tuple[float, float]:
    """Return (extra transit, storage hold), preserving legacy store-option semantics."""
    if opt.hold_h is None:
        return (0.0, float(opt.extra_h)) if opt.is_store else (float(opt.extra_h), 0.0)
    return float(opt.extra_h), float(opt.hold_h)


def build(lot: Lot, opt: Option, shocks: Shocks, p: ProductParams) -> ConditionFeatures:
    """Features of ``opt`` applied to ``lot`` under the draws ``shocks`` (called by P1)."""
    detour_h, hold_h = option_durations(opt)
    return assemble(
        p,
        maturity=lot.maturity,
        packaging=lot.packaging,
        age_h=lot.age_h,
        remaining_h=lot.remaining_h,
        temp_air_c=lot.temp_c,
        delay_h=lot.delay_h,
        diurnal_amp_c=lot.diurnal_amp_c,
        temp_shock_c=shocks.temp,
        transit_factor=shocks.transit,
        extra_h=detour_h,
        hold_h=hold_h,
        temp_offset_c=opt.temp_offset,
        storage_mode=opt.storage_mode,
        product=lot.product,
    )


def out_of_range_features(f: ConditionFeatures, p: ProductParams) -> tuple[str, ...]:
    """Return features outside configured model-calibration bounds.

    This is diagnostic only: the kinetic reference model keeps the physical values, while
    statistical models may clip them at their inference boundary. Warnings are explicit so
    callers cannot confuse extrapolation with validated model support.
    """
    outside: list[str] = []
    ranges = p.calibration_ranges or p.valid_ranges
    for name, bounds in ranges.items():
        if name not in MODEL_COLUMNS:
            continue
        values = np.asarray(getattr(f, name), dtype=float)
        if np.any((values < bounds["min"]) | (values > bounds["max"])):
            outside.append(name)
    return tuple(sorted(outside))


def out_of_range_mask(f: ConditionFeatures, p: ProductParams) -> np.ndarray:
    """Return a flattened row mask for features outside calibration support."""
    matrix = to_matrix(f)
    mask = np.zeros(matrix.shape[0], dtype=bool)
    ranges = p.calibration_ranges or p.valid_ranges
    for name, bounds in ranges.items():
        if name not in MODEL_COLUMNS:
            continue
        values = matrix[:, MODEL_COLUMNS.index(name)]
        mask |= (values < bounds["min"]) | (values > bounds["max"])
    return mask


def with_changes(
    f: ConditionFeatures, p: ProductParams, **changes: Any
) -> ConditionFeatures:
    """Counterfactual copy of ``f``; derived fields are recomputed consistently.

    Allowed keys: age_h, remaining_transit_h, delay_h, hold_h, temp_mean_c,
    diurnal_amp_c, maturity, packaging, storage_mode.
    """
    allowed = {
        "age_h",
        "remaining_transit_h",
        "delay_h",
        "hold_h",
        "temp_mean_c",
        "diurnal_amp_c",
        "maturity",
        "packaging",
        "storage_mode",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Unsupported changes: {sorted(unknown)}")
    amp = (
        np.asarray(f.diurnal_amp_c, dtype=float)
        if f.diurnal_amp_c is not None
        else np.maximum(
            np.asarray(f.temp_max_c, float) - np.asarray(f.temp_mean_c, float), 0.0
        )
    )
    if "diurnal_amp_c" in changes:
        amp = _nonneg(_arr(changes["diurnal_amp_c"], "diurnal_amp_c"), "diurnal_amp_c")
    age = _nonneg(_arr(changes.get("age_h", f.age_h), "age_h"), "age_h")
    rem = _nonneg(
        _arr(
            changes.get("remaining_transit_h", f.remaining_transit_h),
            "remaining_transit_h",
        ),
        "remaining_transit_h",
    )
    hold = _nonneg(_arr(changes.get("hold_h", f.hold_h), "hold_h"), "hold_h")
    delay = _nonneg(_arr(changes.get("delay_h", f.delay_h), "delay_h"), "delay_h")
    if ("remaining_transit_h" in changes or "delay_h" in changes) and np.any(
        delay > rem + 1e-9
    ):
        raise ValueError("delay_h cannot exceed remaining_transit_h")
    for key in ("maturity", "packaging", "storage_mode"):
        if key in changes:
            lookup(CODE_MAPS[key], changes[key], key)
    storage_mode = changes.get("storage_mode", f.storage_mode)
    lookup(STORAGE_CODES_FLOAT, storage_mode, "storage_mode")
    active_storage_mode = np.where(np.asarray(hold) > 0, storage_mode, "none")
    phase_metadata = (
        f.history_temp_mean_c,
        f.transit_temp_mean_c,
        f.storage_temp_mean_c,
    )
    hidden: dict[str, Any]
    derived: dict[str, np.ndarray]
    if all(value is not None for value in phase_metadata):
        history_temp, transit_temp, storage_temp = (
            np.asarray(value, dtype=float).copy() for value in phase_metadata
        )
        if "packaging" in changes:
            old_delta = lookup(p.pack_delta_c, f.packaging, "packaging")
            new_delta = lookup(p.pack_delta_c, changes["packaging"], "packaging")
            shift = np.asarray(new_delta, dtype=float) - np.asarray(
                old_delta, dtype=float
            )
            history_temp += shift
            transit_temp += shift
            storage_temp += shift
        if "storage_mode" in changes:
            storage_offset = lookup(
                p.storage_temp_offset_c, changes["storage_mode"], "storage_mode"
            )
            storage_temp = transit_temp + np.asarray(storage_offset, dtype=float)
        if "temp_mean_c" in changes:
            target_mean = _arr(changes["temp_mean_c"], "temp_mean_c")
            current_mean = _phase_statistics(
                p, history_temp, transit_temp, storage_temp, age, rem, hold, amp
            )["temp_mean_c"]
            shift = target_mean - current_mean
            history_temp += shift
            transit_temp += shift
            storage_temp += shift
        storage_temp = np.where(np.asarray(hold) > 0, storage_temp, transit_temp)
        stats = _phase_statistics(
            p, history_temp, transit_temp, storage_temp, age, rem, hold, amp
        )
        derived = stats
        hidden = {
            "thermal_rate_factor": _unwrap(stats["thermal_rate_factor"]),
            "historical_rate_factor": _unwrap(stats["historical_rate_factor"]),
            "future_rate_factor": _unwrap(stats["future_rate_factor"]),
            "history_temp_mean_c": _unwrap(history_temp),
            "transit_temp_mean_c": _unwrap(transit_temp),
            "storage_temp_mean_c": _unwrap(storage_temp),
            "diurnal_amp_c": _unwrap(amp),
        }
    else:
        temp_mean = _arr(changes.get("temp_mean_c", f.temp_mean_c), "temp_mean_c")
        exposure = age + rem + hold
        derived = {
            "temp_mean_c": temp_mean,
            "temp_max_c": temp_mean + amp,
            "degree_hours_above_ref": np.maximum(temp_mean - p.t_ref_c, 0.0) * exposure,
            "exposure_h": exposure,
        }
        hidden = {
            "thermal_rate_factor": None,
            "historical_rate_factor": None,
            "future_rate_factor": None,
            "history_temp_mean_c": None,
            "transit_temp_mean_c": None,
            "storage_temp_mean_c": None,
            "diurnal_amp_c": None,
        }
    return replace(
        f,
        maturity=changes.get("maturity", f.maturity),
        packaging=changes.get("packaging", f.packaging),
        storage_mode=(
            str(active_storage_mode)
            if np.ndim(active_storage_mode) == 0
            else np.asarray(active_storage_mode, dtype=object)
        ),
        age_h=_unwrap(age),
        remaining_transit_h=_unwrap(rem),
        delay_h=_unwrap(delay),
        hold_h=_unwrap(hold),
        temp_mean_c=_unwrap(derived["temp_mean_c"]),
        temp_max_c=_unwrap(derived["temp_max_c"]),
        exposure_h=_unwrap(derived["exposure_h"]),
        degree_hours_above_ref=_unwrap(derived["degree_hours_above_ref"]),
        **hidden,
    )


def n_rows(f: ConditionFeatures) -> int:
    """Number of rows after broadcasting all fields (1 if everything is scalar)."""
    shapes = [np.shape(getattr(f, n)) for n in MODEL_COLUMNS]
    return int(np.prod(np.broadcast_shapes(*shapes))) if shapes else 1


def to_matrix(
    f: ConditionFeatures, columns: tuple[str, ...] = MODEL_COLUMNS
) -> np.ndarray:
    """Numeric matrix (n_rows, n_columns); categorical columns become integer codes."""
    shape = np.broadcast_shapes(*[np.shape(getattr(f, n)) for n in MODEL_COLUMNS])
    shape = shape if shape else (1,)
    cols = []
    for name in columns:
        v = getattr(f, name)
        if name in CODE_MAPS:
            v = lookup({k: float(c) for k, c in CODE_MAPS[name].items()}, v, name)
        cols.append(np.broadcast_to(np.asarray(v, dtype=float), shape).ravel())
    return np.column_stack(cols)


def from_arrays(cols: Mapping[str, Any], product: str = "tomato") -> ConditionFeatures:
    """Rebuild ConditionFeatures from stored columns (e.g. a dataset)."""
    missing = [c for c in MODEL_COLUMNS if c not in cols]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")

    def get(name: str) -> Any:
        v = cols[name]
        v = v.to_numpy() if hasattr(v, "to_numpy") else v
        return (
            np.asarray(v, dtype=object)
            if name in CATEGORICAL_FEATURES
            else _arr(v, name)
        )

    values = {c: get(c) for c in MODEL_COLUMNS}
    active_storage_mode = np.where(
        np.asarray(values["hold_h"], dtype=float) > 0,
        values["storage_mode"],
        "none",
    )
    values["storage_mode"] = (
        str(active_storage_mode)
        if np.ndim(active_storage_mode) == 0
        else np.asarray(active_storage_mode, dtype=object)
    )
    return ConditionFeatures(product=product, **values)
