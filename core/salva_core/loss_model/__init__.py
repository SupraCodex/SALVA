"""Loss models and the factory used by the backend and the simulation engine.

    from salva_core.loss_model import get_loss_model
    model = get_loss_model()          # production model (kinetic unless LightGBM is GO)

Production defaults to the kinetic model.  LightGBM is used only if
ml/artifacts/active.json says so (written by ml/register.py after a GO verdict) AND the
package loads cleanly; otherwise the factory falls back to the kinetic model.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ..contracts import LossModel
from ..params import ProductParams, load_product, repo_root
from .kinetic_model import KineticLossModel

log = logging.getLogger(__name__)
__all__ = ["KineticLossModel", "active_config_path", "get_experimental_loss_model", "get_loss_model"]


def active_config_path() -> Path:
    env = os.environ.get("SALVA_ACTIVE_MODEL_PATH")
    return Path(env) if env else repo_root() / "ml" / "artifacts" / "active.json"


def _read_active(path: Path | None) -> dict:
    p = Path(path) if path else active_config_path()
    if p.exists():
        return json.loads(p.read_text())
    return {"production": "kinetic", "experimental": None}


def _load_lgbm(name: str, params: ProductParams, active: Path | None) -> LossModel:
    from .lgbm_model import LightGbmLossModel

    base = (Path(active).parent if active else active_config_path().parent) / "models" / name
    return LightGbmLossModel.load(base, params)


def get_loss_model(active_json: Path | None = None, params: ProductParams | None = None) -> LossModel:
    """Return the PRODUCTION loss model. Never raises because of the ML package."""
    params = params or load_product()
    cfg = _read_active(active_json)
    name = cfg.get("production", "kinetic")
    if name != "kinetic":
        try:
            return _load_lgbm(name, params, active_json)
        except Exception as exc:  # noqa: BLE001 - production must keep working
            log.warning("Cannot load %s (%s); falling back to the kinetic model", name, exc)
    return KineticLossModel(params)


def get_experimental_loss_model(active_json: Path | None = None,
                                params: ProductParams | None = None) -> LossModel | None:
    """Return the experimental model (e.g. LightGBM after NO-GO) or None."""
    params = params or load_product()
    name = _read_active(active_json).get("experimental")
    if not name:
        return None
    try:
        return _load_lgbm(name, params, active_json)
    except Exception as exc:  # noqa: BLE001
        log.warning("Cannot load experimental model %s (%s)", name, exc)
        return None
