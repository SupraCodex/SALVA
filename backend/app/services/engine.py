"""Adapter to the scientific core (``salva_core``). The API contains no scientific logic.

The production loss model is chosen by ``ml/artifacts/active.json`` through
``salva_core.loss_model.get_loss_model``: LightGBM only after a GO verdict, otherwise the
kinetic reference model. Any loading failure falls back to the kinetic model (§20).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import yaml
from salva_core.loss_model import KineticLossModel, active_config_path, get_loss_model
from salva_core.params import ParamsError, ProductParams, load_products

from app.config import get_settings
from app.errors import ApiError

log = logging.getLogger("salva.engine")


def _products_path() -> Path:
    return get_settings().reference_dir / "products.yaml"


@lru_cache
def products() -> dict[str, ProductParams]:
    try:
        return load_products(_products_path())
    except ParamsError as exc:
        log.error("product_parameters_invalid", extra={"reason": str(exc)[:200]})
        raise ApiError(503, "engine-unavailable", "Product parameters are unavailable.") from exc


@lru_cache
def products_document() -> dict:
    """Raw products.yaml (labels, descriptions, units, sources) for the assumptions page."""
    return yaml.safe_load(_products_path().read_text(encoding="utf-8"))


def params(product_code: str) -> ProductParams:
    table = products()
    if product_code not in table:
        raise ApiError(422, "unknown-product", f"Unknown product '{product_code}'.")
    return table[product_code]


def product_label(product_code: str, lang: str) -> str:
    entry = products_document().get(product_code, {})
    return entry.get("label", {}).get(lang, product_code)


@lru_cache
def loss_model(product_code: str = "tomato"):
    p = params(product_code)
    model = get_loss_model(params=p)
    return model


def model_descriptor(model) -> dict:
    """Name/version/fallback flag stored with every analysis (NFR-06)."""
    is_kinetic = isinstance(model, KineticLossModel)
    registry = registry_info()
    wanted = registry.get("production", "kinetic")
    return {
        "name": "kinetic" if is_kinetic else "lightgbm",
        "version": model.version,
        # A fallback means the registry asked for another model that could not be loaded.
        "fallback": bool(is_kinetic and wanted != "kinetic"),
    }


@lru_cache
def registry_info() -> dict:
    path = active_config_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
    return {"production": "kinetic", "experimental": None}


def reset_caches() -> None:
    for fn in (products, products_document, loss_model, registry_info):
        fn.cache_clear()
