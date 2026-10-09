"""Loading and validation of product parameters (data/reference/products.yaml).

Every parameter must carry a value, a unit, a description and a source
(``literature`` | ``interview`` | ``assumption``).  Incomplete entries are rejected so
that no constant can silently enter the model without provenance.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

VALID_SOURCES = ("literature", "interview", "assumption")
VALID_RANGE_FEATURES = {
    "age_h",
    "temp_mean_c",
    "temp_max_c",
    "degree_hours_above_ref",
    "remaining_transit_h",
    "delay_h",
    "exposure_h",
}
EXPECTED_MATURITIES = {"green", "breaker", "ripe"}
EXPECTED_PACKAGINGS = {"crate", "carton", "sack"}
EXPECTED_STORAGE_MODES = {"none", "ambient_shade", "ventilated", "cold_room"}
REQUIRED_SCALARS = (
    "t_ref_c",
    "k_ref",
    "q10",
    "sigma_h",
    "sigma_lot",
    "delta",
    "default_diurnal_amp_c",
    "shelf_life_loss_threshold",
)
REQUIRED_MAPPINGS = (
    "maturity",
    "pack_delta_c",
    "pack_damage",
    "storage_temp_offset_c",
    "risk_thresholds",
)


class ParamsError(ValueError):
    """Raised when products.yaml is missing, malformed or scientifically inconsistent."""


def repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (or this file) to the folder holding data/reference."""
    env = os.environ.get("SALVA_REPO_ROOT")
    if env:
        return Path(env)
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "data" / "reference" / "products.yaml").exists():
            return parent
    raise ParamsError(
        "Cannot locate data/reference/products.yaml (set SALVA_REPO_ROOT)."
    )


def default_products_path() -> Path:
    """Return the repository file containing versioned product parameters."""
    return repo_root() / "data" / "reference" / "products.yaml"


@dataclass(frozen=True)
class ProductParams:
    """Validated kinetic parameters of one product."""

    name: str
    t_ref_c: float
    k_ref: float
    q10: float
    sigma_h: float
    sigma_lot: float
    delta: float
    default_diurnal_amp_c: float
    maturity: dict[str, float]
    pack_delta_c: dict[str, float]
    pack_damage: dict[str, float]
    storage_temp_offset_c: dict[str, float]
    grades: tuple[tuple[float, float], ...]
    shelf_life_loss_threshold: float
    risk_thresholds: dict[str, float]
    valid_ranges: dict[str, dict[str, float]] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    file_sha256: str = ""

    @property
    def maturity_order(self) -> tuple[str, ...]:
        """Return maturity categories from lowest to highest decay multiplier."""
        return tuple(sorted(self.maturity, key=lambda k: self.maturity[k]))

    def storage_offset(self, mode: str) -> float:
        """Temperature offset (degC) of a storage mode; use it for Option.temp_offset."""
        try:
            return self.storage_temp_offset_c[mode]
        except KeyError as exc:
            raise ParamsError(
                f"Unknown storage mode {mode!r}; allowed: {sorted(self.storage_temp_offset_c)}"
            ) from exc


def lookup(
    mapping: Mapping[str, float | int], keys: Any, what: str = "category"
) -> Any:
    """Vectorised dict lookup. ``keys`` may be a str or an array of str."""
    if isinstance(keys, str):
        if keys not in mapping:
            raise ParamsError(f"Unknown {what} {keys!r}; allowed: {sorted(mapping)}")
        return float(mapping[keys])
    arr = np.asarray(keys, dtype=object)
    out = np.empty(arr.shape, dtype=float)
    seen = set(arr.ravel().tolist())
    unknown = seen - set(mapping)
    if unknown:
        raise ParamsError(
            f"Unknown {what} values {sorted(unknown)}; allowed: {sorted(mapping)}"
        )
    for key in seen:
        out[arr == key] = mapping[key]
    return out


def _entry_value(name: str, entry: Any, product: str) -> tuple[Any, str]:
    if not isinstance(entry, dict):
        raise ParamsError(
            f"{product}.{name}: expected a mapping with value/unit/description/source"
        )
    for key in ("value", "unit", "description", "source"):
        if key not in entry or entry[key] in (None, ""):
            raise ParamsError(f"{product}.{name}: missing '{key}'")
    if entry["source"] not in VALID_SOURCES:
        raise ParamsError(f"{product}.{name}: source must be one of {VALID_SOURCES}")
    if entry["source"] == "literature" and not entry.get("reference"):
        raise ParamsError(
            f"{product}.{name}: source 'literature' requires a 'reference'"
        )
    return entry["value"], entry["source"]


def _as_finite_float(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise ParamsError(f"{context}: boolean is not a numeric parameter")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ParamsError(f"{context}: expected a finite number") from exc
    if not np.isfinite(result):
        raise ParamsError(f"{context}: expected a finite number")
    return result


def _validate(p: ProductParams) -> None:
    scalar_values = (
        p.t_ref_c,
        p.k_ref,
        p.q10,
        p.sigma_h,
        p.sigma_lot,
        p.delta,
        p.default_diurnal_amp_c,
        p.shelf_life_loss_threshold,
    )
    if not all(np.isfinite(value) for value in scalar_values):
        raise ParamsError(f"{p.name}: scalar parameters must all be finite")
    for key, mapping in (
        ("maturity", p.maturity),
        ("pack_delta_c", p.pack_delta_c),
        ("pack_damage", p.pack_damage),
        ("storage_temp_offset_c", p.storage_temp_offset_c),
        ("risk_thresholds", p.risk_thresholds),
    ):
        if not all(np.isfinite(value) for value in mapping.values()):
            raise ParamsError(f"{p.name}.{key}: values must all be finite")
    for key, mapping, expected in (
        ("maturity", p.maturity, EXPECTED_MATURITIES),
        ("pack_delta_c", p.pack_delta_c, EXPECTED_PACKAGINGS),
        ("pack_damage", p.pack_damage, EXPECTED_PACKAGINGS),
        ("storage_temp_offset_c", p.storage_temp_offset_c, EXPECTED_STORAGE_MODES),
    ):
        if set(mapping) != expected:
            raise ParamsError(
                f"{p.name}.{key}: expected categories {sorted(expected)}, "
                f"got {sorted(mapping)}"
            )
    if not isinstance(p.valid_ranges, dict):
        raise ParamsError(f"{p.name}.valid_ranges must be a mapping")
    for feature, bounds in p.valid_ranges.items():
        try:
            lower = _as_finite_float(
                bounds["min"], f"{p.name}.valid_ranges.{feature}.min"
            )
            upper = _as_finite_float(
                bounds["max"], f"{p.name}.valid_ranges.{feature}.max"
            )
            valid_bounds = (
                isinstance(bounds, dict)
                and {"min", "max"} <= set(bounds)
                and np.isfinite(lower)
                and np.isfinite(upper)
                and lower <= upper
            )
        except (KeyError, TypeError, ValueError):
            valid_bounds = False
        if feature not in VALID_RANGE_FEATURES or not valid_bounds:
            raise ParamsError(
                f"{p.name}.valid_ranges.{feature}: expected finite min <= max"
            )
    if not (p.k_ref > 0 and p.q10 >= 1 and p.sigma_h > 0 and p.sigma_lot >= 0):
        raise ParamsError(
            f"{p.name}: k_ref>0, q10>=1, sigma_h>0, sigma_lot>=0 required"
        )
    if not 0 <= p.delta <= 1:
        raise ParamsError(f"{p.name}: delta must be in [0, 1]")
    if p.default_diurnal_amp_c < 0:
        raise ParamsError(f"{p.name}: default_diurnal_amp_c must be >= 0")
    if not 0 < p.shelf_life_loss_threshold < 1:
        raise ParamsError(f"{p.name}: shelf_life_loss_threshold must be in (0, 1)")
    required_risk = {
        "low_p50_max",
        "medium_p50_max",
        "low_width_max",
        "medium_width_max",
    }
    if set(p.risk_thresholds) != required_risk:
        raise ParamsError(
            f"{p.name}: risk_thresholds must contain {sorted(required_risk)}"
        )
    if not all(0 < v < 1 for v in p.risk_thresholds.values()):
        raise ParamsError(f"{p.name}: risk thresholds must be in (0, 1)")
    if not p.risk_thresholds["low_p50_max"] < p.risk_thresholds["medium_p50_max"]:
        raise ParamsError(f"{p.name}: low_p50_max must be below medium_p50_max")
    if not p.risk_thresholds["low_width_max"] <= p.risk_thresholds["medium_width_max"]:
        raise ParamsError(f"{p.name}: low_width_max must be <= medium_width_max")
    order = p.maturity_order
    vals = [p.maturity[k] for k in order]
    if any(v <= 0 for v in vals) or len(set(vals)) != len(vals):
        raise ParamsError(
            f"{p.name}: maturity multipliers must be positive and distinct"
        )
    for k, v in p.pack_damage.items():
        if not 0 <= v < 1:
            raise ParamsError(f"{p.name}: pack_damage[{k}] must be in [0, 1)")
    ths = [g[0] for g in p.grades]
    mults = [g[1] for g in p.grades]
    if not ths or any(not 0 < t < 1 for t in ths) or ths != sorted(ths, reverse=True):
        raise ParamsError(
            f"{p.name}: grade thresholds must be strictly decreasing in (0, 1)"
        )
    if len(set(ths)) != len(ths):
        raise ParamsError(f"{p.name}: grade thresholds must be distinct")
    if any(not 0 <= m <= 1 for m in mults) or mults != sorted(mults, reverse=True):
        raise ParamsError(
            f"{p.name}: grade multipliers must be decreasing within [0, 1]"
        )
    if len(p.grades) != 3:
        raise ParamsError(
            f"{p.name}: exactly 3 grade thresholds (A, B, C) are supported"
        )
    if "none" not in p.storage_temp_offset_c:
        raise ParamsError(f"{p.name}: storage_temp_offset_c needs a 'none' entry")


def load_products(path: Path | str | None = None) -> dict[str, ProductParams]:
    """Load and validate every product of the YAML file."""
    p = Path(path) if path else default_products_path()
    if not p.exists():
        raise ParamsError(f"Products file not found: {p}")
    raw_bytes = p.read_bytes()
    doc = yaml.safe_load(raw_bytes)
    if not isinstance(doc, dict):
        raise ParamsError("Products file root must be a mapping")
    sha = hashlib.sha256(raw_bytes).hexdigest()
    products: dict[str, ProductParams] = {}
    for name, body in doc.items():
        if name == "schema_version":
            continue
        if not isinstance(body, dict):
            raise ParamsError(f"{name}: product entry must be a mapping")
        params = body.get("parameters", {})
        if not isinstance(params, dict):
            raise ParamsError(f"{name}.parameters must be a mapping")
        sources: dict[str, str] = {}
        scalars: dict[str, float] = {}
        mappings: dict[str, dict[str, float]] = {}
        for key in REQUIRED_SCALARS:
            if key not in params:
                raise ParamsError(f"{name}: missing parameter '{key}'")
            val, src = _entry_value(key, params[key], name)
            scalars[key] = _as_finite_float(val, f"{name}.{key}")
            sources[key] = src
        for key in REQUIRED_MAPPINGS:
            if key not in params:
                raise ParamsError(f"{name}: missing parameter '{key}'")
            val, src = _entry_value(key, params[key], name)
            if not isinstance(val, dict) or not val:
                raise ParamsError(f"{name}.{key}: value must be a non-empty mapping")
            mappings[key] = {
                str(k): _as_finite_float(v, f"{name}.{key}.{k}") for k, v in val.items()
            }
            sources[key] = src
        if "grades" not in params:
            raise ParamsError(f"{name}: missing parameter 'grades'")
        gval, gsrc = _entry_value("grades", params["grades"], name)
        sources["grades"] = gsrc
        if not isinstance(gval, (list, tuple)):
            raise ParamsError(
                f"{name}.grades: expected a list of threshold/multiplier pairs"
            )
        try:
            grades = tuple(
                (
                    _as_finite_float(a, f"{name}.grades.threshold"),
                    _as_finite_float(b, f"{name}.grades.multiplier"),
                )
                for a, b in gval
            )
        except (TypeError, ValueError) as exc:
            raise ParamsError(
                f"{name}.grades: expected threshold/multiplier pairs"
            ) from exc
        valid_ranges = body.get("valid_ranges", {})
        if not isinstance(valid_ranges, dict):
            raise ParamsError(f"{name}.valid_ranges must be a mapping")
        product = ProductParams(
            name=name,
            t_ref_c=scalars["t_ref_c"],
            k_ref=scalars["k_ref"],
            q10=scalars["q10"],
            sigma_h=scalars["sigma_h"],
            sigma_lot=scalars["sigma_lot"],
            delta=scalars["delta"],
            default_diurnal_amp_c=scalars["default_diurnal_amp_c"],
            shelf_life_loss_threshold=scalars["shelf_life_loss_threshold"],
            maturity=mappings["maturity"],
            pack_delta_c=mappings["pack_delta_c"],
            pack_damage=mappings["pack_damage"],
            storage_temp_offset_c=mappings["storage_temp_offset_c"],
            risk_thresholds=mappings["risk_thresholds"],
            grades=grades,
            valid_ranges=valid_ranges,
            sources=sources,
            file_sha256=sha,
        )
        _validate(product)
        products[name] = product
    if not products:
        raise ParamsError("No product defined in products.yaml")
    return products


def load_product(name: str = "tomato", path: Path | str | None = None) -> ProductParams:
    """Load one named product after validating the complete reference file."""
    products = load_products(path)
    if name not in products:
        raise ParamsError(f"Unknown product {name!r}; available: {sorted(products)}")
    return products[name]
