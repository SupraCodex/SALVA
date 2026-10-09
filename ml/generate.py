"""Synthetic dataset generation (P3).

DATA TYPE = SYNTHETIC.  GENERATOR = KINETIC MODEL.  Labels come from salva_core.kinetics;
features come from salva_core.features.assemble: there is NO second copy of the equations
or of the feature logic here.

Structure: the data are organised in LOTS.  A lot has fixed maturity, packaging, base
temperature, daily amplitude and a hidden lot variability ``u`` (so k_lot is shared by all
its rows); each row is a different observed state (age, remaining transit, delay, shocks,
optional storage).  Rows of a lot are correlated, hence splits are done per lot.

Reproducibility: dataset = f(seed, config, products.yaml, generator version).

    python -m ml.generate --seed 42 --n-lots 4000 --rows-per-lot 40
"""

from __future__ import annotations

import argparse
import logging
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from salva_core import features as F
from salva_core import kinetics
from salva_core.loss_model.kinetic_model import KineticLossModel
from salva_core.params import ProductParams, load_product
from scipy.special import ndtri
from scipy.stats import qmc

from .config import ARTIFACTS_DIR, load_config, sha256_json
from .io_utils import dataframe_hash, save_dataset

log = logging.getLogger("ml.generate")
GENERATOR_VERSION = "1.0.0"
TARGET = "loss"
HIDDEN_COLUMNS = ("hidden_u", "hidden_mean_quality")   # NEVER features
ID_COLUMNS = ("lot_id", "row_id", "product")
_U_EPS = 1e-6


def _scaled(u: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return lo + (hi - lo) * u


def generate_dataset(
    cfg: dict[str, Any],
    params: ProductParams,
    *,
    n_lots: int | None = None,
    rows_per_lot: int | None = None,
    seed: int | None = None,
) -> pd.DataFrame:
    g, s = cfg["generator"], cfg["sampling"]
    n_lots = int(n_lots if n_lots is not None else g["n_lots"])
    rows_per_lot = int(rows_per_lot if rows_per_lot is not None else g["rows_per_lot"])
    seed = int(seed if seed is not None else g["seed"])
    if n_lots < 1 or rows_per_lot < 1:
        raise ValueError("n_lots and rows_per_lot must be >= 1")
    n = n_lots * rows_per_lot

    ss = np.random.SeedSequence(seed)
    rng_lot, rng_lhs = (np.random.default_rng(c) for c in ss.spawn(2))
    lhs_seed = int(rng_lhs.integers(0, 2**31 - 1))

    # ---- lot level -------------------------------------------------------------
    mats = list(s["maturity_probs"])
    packs = list(s["packaging_probs"])
    lot_mat = rng_lot.choice(mats, size=n_lots, p=[s["maturity_probs"][m] for m in mats])
    lot_pack = rng_lot.choice(packs, size=n_lots, p=[s["packaging_probs"][k] for k in packs])
    lot_temp = _scaled(rng_lot.random(n_lots), s["temp_air_c"]["min"], s["temp_air_c"]["max"])
    lot_amp = _scaled(rng_lot.random(n_lots), s["diurnal_amp_c"]["min"], s["diurnal_amp_c"]["max"])
    lot_u = np.clip(rng_lot.random(n_lots), _U_EPS, 1 - _U_EPS)

    rep = lambda a: np.repeat(a, rows_per_lot)
    maturity, packaging = rep(lot_mat).astype(object), rep(lot_pack).astype(object)
    temp_air, amp, u_row = rep(lot_temp), rep(lot_amp), rep(lot_u)

    # ---- row level (Latin hypercube for coverage) -------------------------------
    z = qmc.LatinHypercube(d=8, seed=lhs_seed).random(n)
    age = _scaled(z[:, 0], s["age_h"]["min"], s["age_h"]["max"])
    planned = _scaled(z[:, 1], s["remaining_planned_h"]["min"], s["remaining_planned_h"]["max"])
    d = s["delay_h"]
    v = np.clip((z[:, 2] - d["p_zero"]) / (1.0 - d["p_zero"]), 0.0, 1.0 - 1e-9)
    delay = np.where(z[:, 2] < d["p_zero"], 0.0, np.minimum(-d["mean"] * np.log1p(-v), d["max"]))
    remaining = planned + delay
    shock = s["temp_shock_sd_c"] * ndtri(np.clip(z[:, 3], _U_EPS, 1 - _U_EPS))
    transit = np.exp(s["transit_sigma"] * ndtri(np.clip(z[:, 4], _U_EPS, 1 - _U_EPS)))
    modes = list(s["storage_modes"])
    has_storage = z[:, 5] < s["p_storage"]
    mode_idx = np.minimum((z[:, 7] * len(modes)).astype(int), len(modes) - 1)
    storage_mode = np.where(has_storage, np.array(modes, dtype=object)[mode_idx], "none").astype(object)
    hold = np.where(has_storage, _scaled(z[:, 6], s["storage_hold_h"]["min"], s["storage_hold_h"]["max"]), 0.0)
    offset = np.array([params.storage_offset(m) for m in storage_mode], dtype=float)

    f = F.assemble(
        params, maturity=maturity, packaging=packaging, age_h=age, remaining_h=remaining,
        temp_air_c=temp_air, delay_h=delay, diurnal_amp_c=amp, temp_shock_c=shock,
        transit_factor=transit, extra_h=hold, temp_offset_c=offset, storage_mode=storage_mode,
        product=params.name,
    )
    model = KineticLossModel(params)
    quality, loss = kinetics.quality_and_loss(f, model.lot_multiplier(u_row), params)

    df = pd.DataFrame({
        "lot_id": np.repeat(np.arange(n_lots), rows_per_lot),
        "row_id": np.arange(n),
        "product": params.name,
        **{c: np.asarray(getattr(f, c)) for c in F.MODEL_COLUMNS},
        TARGET: np.asarray(loss, dtype=float),
        "hidden_u": u_row,
        "hidden_mean_quality": np.asarray(quality, dtype=float),
    })
    return df


def build_metadata(cfg: dict[str, Any], params: ProductParams, df: pd.DataFrame, seed: int,
                   n_lots: int, rows_per_lot: int) -> dict[str, Any]:
    ds_hash = dataframe_hash(df)
    return {
        "DATA_TYPE": "SYNTHETIC",
        "GENERATOR": "KINETIC MODEL",
        "SEED": seed,
        "VERSION": GENERATOR_VERSION,
        "dataset_id": f"synth-g{GENERATOR_VERSION}-s{seed}-{ds_hash[:8]}",
        "dataset_hash": ds_hash,
        "n_rows": len(df), "n_lots": n_lots, "rows_per_lot": rows_per_lot,
        "product": params.name,
        "products_yaml_sha256": params.file_sha256,
        "parameter_sources": params.sources,
        "config_sha256": sha256_json({"generator": cfg["generator"], "sampling": cfg["sampling"]}),
        "feature_version": F.FEATURE_VERSION,
        "feature_schema_hash": F.schema_hash(),
        "target": TARGET,
        "hidden_columns": list(HIDDEN_COLUMNS),
        "model_columns": list(F.MODEL_COLUMNS),
        "warning": "Synthetic labels computed by the kinetic model. Not field observations.",
        "dependencies": {"python": platform.python_version(), "numpy": np.__version__,
                         "scipy": scipy.__version__, "pandas": pd.__version__},
        "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def run(config: Path | str | None = None, *, n_lots: int | None = None,
        rows_per_lot: int | None = None, seed: int | None = None,
        out_dir: Path | str | None = None) -> Path:
    cfg = load_config(config)
    params = load_product(cfg["product"])
    g = cfg["generator"]
    n_lots = int(n_lots if n_lots is not None else g["n_lots"])
    rows_per_lot = int(rows_per_lot if rows_per_lot is not None else g["rows_per_lot"])
    seed = int(seed if seed is not None else g["seed"])
    df = generate_dataset(cfg, params, n_lots=n_lots, rows_per_lot=rows_per_lot, seed=seed)
    meta = build_metadata(cfg, params, df, seed, n_lots, rows_per_lot)
    root = Path(out_dir) if out_dir else ARTIFACTS_DIR / "datasets"
    folder = save_dataset(df, meta, root / meta["dataset_id"])
    log.info("dataset %s: %d rows, %d lots -> %s", meta["dataset_id"], len(df), n_lots, folder)
    return folder


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Generate the SYNTHETIC training dataset")
    ap.add_argument("--config", default=None)
    ap.add_argument("--n-lots", type=int, default=None)
    ap.add_argument("--rows-per-lot", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=None, help="parent folder (default ml/artifacts/datasets)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(run(a.config, n_lots=a.n_lots, rows_per_lot=a.rows_per_lot, seed=a.seed, out_dir=a.out))


if __name__ == "__main__":
    main()
