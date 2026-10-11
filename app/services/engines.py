"""Adapter to the scientific engine `salva_core` (core/, owned by R4/R5 — NOT part of the API code).

The API depends only on the public functions listed in the coding guide §4:
    salva_core.params.load_products(path)            -> {code: ProductParams}
    salva_core.loss_model.KineticLossModel(params)   -> .sample_loss(features, u), .risk_level(p50), .version
    salva_core.loss_model.factors.top_factors(model, lot, params)
    salva_core.loss_model.sampling.quantiles(array)
    salva_core.features.build(lot, option|None, shocks, params)
    salva_core.simulation.draw(n, seed), salva_core.simulation.run_all(model, lot, scenarios, shocks, params)
    salva_core.recommendation.recommend(results, policy, lot), salva_core.recommendation.policy_for(profile)
    salva_core.contracts.{Lot, Market, Option, Scenario}

If core is not installed (or products.yaml is missing), analysis endpoints answer 503 with a clear code.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.errors import ApiError


def _unavailable(why: str) -> ApiError:
    return ApiError(503, "engine-unavailable", f"Scientific engine unavailable: {why}")


@lru_cache
def products() -> dict:
    try:
        from salva_core.params import load_products
    except ImportError:
        raise _unavailable("package `salva_core` is not installed (pip install -e core)") from None
    path = get_settings().reference_dir / "products.yaml"
    if not path.exists():
        raise _unavailable(f"{path.name} not found in data/reference/")
    return load_products(path)


@lru_cache
def loss_model(product: str):
    from salva_core.loss_model import KineticLossModel  # LightGBM (wave 2) plugs in here, same interface
    params = products()
    if product not in params:
        raise _unavailable(f"no parameters for product '{product}'")
    return KineticLossModel(params[product])


def model_info(product: str = "tomato") -> dict | None:
    try:
        m = loss_model(product)
    except ApiError:
        return None
    return {"version": m.version, "fallback": getattr(m, "is_fallback", False)}
