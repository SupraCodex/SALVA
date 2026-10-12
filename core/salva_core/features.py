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

from .contracts import ConditionFeatures, Lot, Option, Shocks
from .params import ParamsError, ProductParams, lookup

FEATURE_VERSION = "1.0.0"
NUMERIC_FEATURES = (
    "age_h", "temp_mean_c", "temp_max_c", "degree_hours_above_ref",
    "remaining_transit_h", "delay_h", "exposure_h",
)
CATEGORICAL_FEATURES = ("maturity", "packaging", "storage_mode")
MODEL_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Integer codes used for model inputs. Changing them requires bumping FEATURE_VERSION.
MATURITY_CODES = {"green": 0, "breaker": 1, "ripe": 2}
PACKAGING_CODES = {"crate": 0, "carton": 1, "sack": 2}
STORAGE_CODES = {"none": 0, "ambient_shade": 1, "ventilated": 2, "cold_room": 3}
CODE_MAPS = {
    "maturity": MATURITY_CODES, "packaging": PACKAGING_CODES, "storage_mode": STORAGE_CODES,
}

# Monotone relationship with the loss (+1: loss never decreases when the feature grows).
MONOTONE_INCREASING = (
    "age_h", "temp_mean_c", "temp_max_c", "degree_hours_above_ref",
    "remaining_transit_h", "delay_h", "exposure_h", "maturity",
)


def feature_schema() -> dict[str, Any]:
    return {
        "version": FEATURE_VERSION,
        "columns": list(MODEL_COLUMNS),
        "numeric": list(NUMERIC_FEATURES),
        "categorical": list(CATEGORICAL_FEATURES),
        "codes": {k: dict(v) for k, v in CODE_MAPS.items()},
        "monotone_increasing": list(MONOTONE_INCREASING),
    }


def schema_hash() -> str:
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
            raise ParamsError(f"{p.name}.{key}: categories {sorted(extra)} unknown to features.py")


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
    temp_offset_c: Any = 0.0,
    storage_mode: Any = "none",
    product: str | None = None,
) -> ConditionFeatures:
    """Build ConditionFeatures from raw conditions (floats or arrays, broadcast together).

    ``remaining_h`` is the hours to arrival INCLUDING the delay ``delay_h``.
    ``extra_h`` (detour or storage hold) is added to it; the sum is scaled by
    ``transit_factor`` (random transit-duration shock).
    """
    check_params_compatible(p)
    age = _nonneg(_arr(age_h, "age_h"), "age_h")
    rem = _nonneg(_arr(remaining_h, "remaining_h"), "remaining_h")
    extra = _nonneg(_arr(extra_h, "extra_h"), "extra_h")
    delay = _nonneg(_arr(delay_h, "delay_h"), "delay_h")
    if np.any(delay > rem + 1e-9):
        raise ValueError("delay_h cannot exceed remaining_h (the delay is part of it)")
    factor = _arr(transit_factor, "transit_factor")
    if np.any(factor <= 0):
        raise ValueError("transit_factor must be > 0")
    air = _arr(temp_air_c, "temp_air_c")
    rng = p.valid_ranges.get("temp_mean_c")
    if rng and (np.any(air < rng["min"]) or np.any(air > rng["max"])):
        raise ValueError(f"temp_air_c must be within [{rng['min']}, {rng['max']}] degC")
    amp = p.default_diurnal_amp_c if diurnal_amp_c is None else diurnal_amp_c
    amp = _nonneg(_arr(amp, "diurnal_amp_c"), "diurnal_amp_c")

    pack_delta = lookup(p.pack_delta_c, packaging, "packaging")
    temp_mean = air + pack_delta + _arr(temp_offset_c, "temp_offset_c") + _arr(temp_shock_c, "temp_shock_c")
    remaining_transit = (rem + extra) * factor
    exposure = age + remaining_transit
    degree_hours = np.maximum(temp_mean - p.t_ref_c, 0.0) * exposure
    lookup(p.maturity, maturity, "maturity")           # validates categories
    lookup(STORAGE_CODES_FLOAT, storage_mode, "storage_mode")
    return ConditionFeatures(
        product=product or p.name,
        maturity=maturity if isinstance(maturity, str) else np.asarray(maturity, dtype=object),
        packaging=packaging if isinstance(packaging, str) else np.asarray(packaging, dtype=object),
        storage_mode=storage_mode if isinstance(storage_mode, str) else np.asarray(storage_mode, dtype=object),
        age_h=_unwrap(age),
        temp_mean_c=_unwrap(temp_mean),
        temp_max_c=_unwrap(temp_mean + amp),
        degree_hours_above_ref=_unwrap(degree_hours),
        remaining_transit_h=_unwrap(remaining_transit),
        delay_h=_unwrap(delay),
        exposure_h=_unwrap(exposure),
    )


STORAGE_CODES_FLOAT = {k: float(v) for k, v in STORAGE_CODES.items()}


def build(lot: Lot, opt: Option, shocks: Shocks, p: ProductParams) -> ConditionFeatures:
    """Features of ``opt`` applied to ``lot`` under the draws ``shocks`` (called by P1)."""
    return assemble(
        p, maturity=lot.maturity, packaging=lot.packaging, age_h=lot.age_h,
        remaining_h=lot.remaining_h, temp_air_c=lot.temp_c, delay_h=lot.delay_h,
        diurnal_amp_c=lot.diurnal_amp_c, temp_shock_c=shocks.temp,
        transit_factor=shocks.transit, extra_h=opt.extra_h, temp_offset_c=opt.temp_offset,
        storage_mode=opt.storage_mode, product=lot.product,
    )


def with_changes(f: ConditionFeatures, p: ProductParams, **changes: Any) -> ConditionFeatures:
    """Counterfactual copy of ``f``; derived fields are recomputed consistently.

    Allowed keys: age_h, remaining_transit_h, delay_h, temp_mean_c (the maximum shifts
    with it), diurnal_amp_c, maturity, packaging, storage_mode.
    """
    allowed = {
        "age_h", "remaining_transit_h", "delay_h", "temp_mean_c",
        "diurnal_amp_c", "maturity", "packaging", "storage_mode",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Unsupported changes: {sorted(unknown)}")
    amp = np.maximum(np.asarray(f.temp_max_c, float) - np.asarray(f.temp_mean_c, float), 0.0)
    if "diurnal_amp_c" in changes:
        amp = _nonneg(_arr(changes["diurnal_amp_c"], "diurnal_amp_c"), "diurnal_amp_c")
    temp_mean = _arr(changes.get("temp_mean_c", f.temp_mean_c), "temp_mean_c")
    age = _nonneg(_arr(changes.get("age_h", f.age_h), "age_h"), "age_h")
    rem = _nonneg(_arr(changes.get("remaining_transit_h", f.remaining_transit_h), "remaining_transit_h"), "remaining_transit_h")
    delay = _nonneg(_arr(changes.get("delay_h", f.delay_h), "delay_h"), "delay_h")
    exposure = age + rem
    for key in ("maturity", "packaging", "storage_mode"):
        if key in changes:
            lookup(CODE_MAPS[key], changes[key], key)
    return replace(
        f,
        maturity=changes.get("maturity", f.maturity),
        packaging=changes.get("packaging", f.packaging),
        storage_mode=changes.get("storage_mode", f.storage_mode),
        age_h=_unwrap(age), remaining_transit_h=_unwrap(rem), delay_h=_unwrap(delay),
        temp_mean_c=_unwrap(temp_mean), temp_max_c=_unwrap(temp_mean + amp),
        exposure_h=_unwrap(exposure),
        degree_hours_above_ref=_unwrap(np.maximum(temp_mean - p.t_ref_c, 0.0) * exposure),
    )


def n_rows(f: ConditionFeatures) -> int:
    """Number of rows after broadcasting all fields (1 if everything is scalar)."""
    shapes = [np.shape(getattr(f, n)) for n in MODEL_COLUMNS]
    return int(np.prod(np.broadcast_shapes(*shapes))) if shapes else 1


def to_matrix(f: ConditionFeatures, columns: tuple[str, ...] = MODEL_COLUMNS) -> np.ndarray:
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
        return np.asarray(v, dtype=object) if name in CATEGORICAL_FEATURES else _arr(v, name)

    return ConditionFeatures(product=product, **{c: get(c) for c in MODEL_COLUMNS})
