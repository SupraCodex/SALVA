"""LightGBM quantile training (offline only, never inside the API).

Pipeline: baseline first -> load train/val -> validate -> build features (the SAME
salva_core.features code as production) -> 7 quantile models with monotone constraints
-> save models + full training log.

    python -m ml.train --split ml/artifacts/splits/<split_dir>
"""

from __future__ import annotations

import argparse
import logging
import platform
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from salva_core import features as F
from salva_core.loss_model.lgbm_model import QUANTILES, QuantileBooster
from salva_core.params import load_product

from . import baseline
from .config import ARTIFACTS_DIR, load_config, sha256_json, write_json
from .metrics import features_from_frame, pinball
from .split import load_split
from .validate import assert_no_forbidden_features, validate_dataframe

log = logging.getLogger("ml.train")
warnings.filterwarnings("ignore", message=".*eval_set.*deprecated.*")
TRAINER_VERSION = "2.0.0"


def monotone_constraints() -> list[int]:
    return [1 if c in F.MONOTONE_INCREASING else 0 for c in F.MODEL_COLUMNS]


def categorical_indices() -> list[int]:
    return [F.MODEL_COLUMNS.index(c) for c in ("packaging", "storage_mode")]


def make_matrix(df: pd.DataFrame, product: str) -> np.ndarray:
    return F.to_matrix(features_from_frame(df, product))


def _pinball_objective(tau: float):
    def objective(y_true: np.ndarray, y_pred: np.ndarray):
        grad = np.where(y_true > y_pred, -tau, 1.0 - tau)
        return grad, np.ones_like(y_pred)         # hessian 1: constant-curvature surrogate
    return objective


def _pinball_metric(tau: float):
    def metric(y_true: np.ndarray, y_pred: np.ndarray):
        d = y_true - y_pred
        return "pinball", float(np.mean(np.maximum(tau * d, (tau - 1.0) * d))), False
    return metric


def fit_quantile_models(x_tr: np.ndarray, y_tr: np.ndarray, x_va: np.ndarray, y_va: np.ndarray,
                        hp: dict[str, Any]) -> tuple[dict[float, QuantileBooster], dict[str, Any]]:
    mode = hp.get("mode", "pinball_custom_monotone")
    if mode not in ("pinball_custom_monotone", "native_quantile"):
        raise ValueError(f"unknown lightgbm.mode {mode!r}")
    models: dict[float, QuantileBooster] = {}
    info: dict[str, Any] = {}
    for q in QUANTILES:
        common = {
            "n_estimators": int(hp["n_estimators"]), "learning_rate": float(hp["learning_rate"]),
            "num_leaves": int(hp["num_leaves"]), "min_child_samples": int(hp["min_child_samples"]),
            "colsample_bytree": float(hp["feature_fraction"]), "random_state": int(hp["seed"]),
            "deterministic": True, "force_row_wise": True, "n_jobs": 1, "verbose": -1,
        }
        cb = [lgb.early_stopping(int(hp["early_stopping_rounds"]), verbose=False)]
        if mode == "native_quantile":
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, **common)
            m.fit(x_tr, y_tr, eval_set=[(x_va, y_va)], categorical_feature=categorical_indices(), callbacks=cb)
            init = 0.0
        else:
            init = float(np.quantile(y_tr, q))
            m = lgb.LGBMRegressor(
                objective=_pinball_objective(q), monotone_constraints=monotone_constraints(),
                monotone_constraints_method=hp.get("monotone_constraints_method", "advanced"), **common)
            m.fit(x_tr, y_tr, init_score=np.full(len(y_tr), init), eval_set=[(x_va, y_va)],
                  eval_init_score=[np.full(len(y_va), init)], eval_metric=_pinball_metric(q),
                  categorical_feature=categorical_indices(), callbacks=cb)
        models[q] = QuantileBooster(m.booster_, init)
        info[f"{q:.2f}"] = {
            "best_iteration": int(m.best_iteration_ or hp["n_estimators"]),
            "val_pinball": pinball(y_va, models[q].predict(x_va), q),
        }
    return models, info


def run(split_dir: Path | str, config: Path | str | None = None, out_dir: Path | str | None = None,
        *, skip_baseline: bool = False) -> Path:
    cfg = load_config(config)
    split_dir = Path(split_dir)
    if not skip_baseline and not (split_dir / "baseline_metrics.json").exists():
        log.info("measuring the kinetic baseline first ...")
        baseline.run(split_dir, config)
    params = load_product(cfg["product"])
    splits = load_split(split_dir)
    manifest = __import__("json").loads((split_dir / "split_manifest.json").read_text())

    for name in ("train", "val"):
        rep = validate_dataframe(splits[name], params, cfg)
        if not rep.ok:
            raise ValueError(f"{name} split failed validation:\n{rep.to_text()}")
    assert_no_forbidden_features(list(F.MODEL_COLUMNS))

    hp = cfg["lightgbm"]
    x_tr, x_va = (make_matrix(splits[n], params.name) for n in ("train", "val"))
    y_tr, y_va = (splits[n]["loss"].to_numpy(float) for n in ("train", "val"))
    t0 = time.perf_counter()
    models, info = fit_quantile_models(x_tr, y_tr, x_va, y_va, hp)
    seconds = time.perf_counter() - t0

    version = f"lgbm-{TRAINER_VERSION}-{manifest['dataset_hash'][:8]}-s{hp['seed']}"
    run_dir = Path(out_dir) if out_dir else ARTIFACTS_DIR / "runs" / version
    run_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(models, run_dir / "models.joblib")
    write_json(run_dir / "train_log.json", {
        "DATA_TYPE": "SYNTHETIC", "model_version": version, "trainer_version": TRAINER_VERSION,
        "seed": int(hp["seed"]), "hyperparameters": hp, "hyperparameters_sha256": sha256_json(hp),
        "dataset_id": manifest["dataset_id"], "dataset_hash": manifest["dataset_hash"],
        "split_row_id_hash": manifest["row_id_hash"], "split_dir": str(split_dir),
        "products_yaml_sha256": params.file_sha256,
        "feature_version": F.FEATURE_VERSION, "feature_schema_hash": F.schema_hash(),
        "feature_columns": list(F.MODEL_COLUMNS), "monotone_constraints": monotone_constraints(), "mode": hp.get("mode"),
        "rows": {"train": len(y_tr), "val": len(y_va)},
        # Labels come from kinetics.quality_and_loss, which already applies chilling injury.
        "loss_includes_chilling_penalty": True,
        # Observed support of the training data: the loss model clips to it at inference
        # and flags extrapolation outside it.
        "calibration_ranges": {
            c: {"min": float(splits["train"][c].min()), "max": float(splits["train"][c].max())}
            for c in F.NUMERIC_FEATURES
        },
        "per_quantile": info, "train_seconds": round(seconds, 2),
        "dependencies": {"python": platform.python_version(), "numpy": np.__version__,
                         "pandas": pd.__version__, "lightgbm": lgb.__version__},
        "command": " ".join(sys.argv),
    })
    log.info("trained %s in %.1fs -> %s", version, seconds, run_dir)
    return run_dir


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Train the LightGBM quantile surrogate")
    ap.add_argument("--split", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--skip-baseline", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(run(a.split, a.config, a.out, skip_baseline=a.skip_baseline))


if __name__ == "__main__":
    main()
