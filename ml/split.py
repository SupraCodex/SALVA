"""Reproducible, leakage-safe split by LOT (P3).

Why per lot?  Rows of one lot share the hidden lot variability and base conditions, so they
are strongly correlated.  A random row split would put siblings in train and test and give
an optimistic evaluation.  We therefore assign whole lots to a split.

Four disjoint groups of LOTS (fractions in ml/params/tomato.yaml, fixed seed):
    train 65% | val 12.5% | test 12.5% | extrapolation 10%
Region rule: rows with effective temperature > X or age > Y are NEVER in train/val/test.
They are dropped there and kept only in the extrapolation lots (``test_extrapolated``),
so the extrapolation set measures behaviour outside the training domain without sharing
any lot with the training data.  The test set is "sealed": use it once, at the end.

    python -m ml.split --dataset ml/artifacts/datasets/<dataset_id>
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import ARTIFACTS_DIR, load_config, sha256_json, write_json
from .io_utils import load_dataset

log = logging.getLogger("ml.split")
SPLITS = ("train", "val", "test", "test_extrapolated")


def assign_lots(lot_ids: np.ndarray, fractions: dict[str, float], seed: int) -> dict[str, np.ndarray]:
    names = ("train", "val", "test", "extrapolation")
    fr = np.array([fractions[n] for n in names], dtype=float)
    if abs(fr.sum() - 1.0) > 1e-9 or (fr <= 0).any():
        raise ValueError("split fractions must be positive and sum to 1")
    ids = np.sort(np.unique(lot_ids))
    if len(ids) < len(names):
        raise ValueError(f"need at least {len(names)} lots, got {len(ids)}")
    perm = np.random.default_rng(seed).permutation(ids)
    cuts = np.floor(np.cumsum(fr)[:-1] * len(ids)).astype(int)
    cuts = np.maximum(cuts, np.arange(1, len(names)))        # every group gets >= 1 lot
    parts = np.split(perm, cuts)
    return dict(zip(names, parts, strict=True))


def split_dataframe(df: pd.DataFrame, cfg_split: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    seed = int(cfg_split["seed"])
    groups = assign_lots(df["lot_id"].to_numpy(), cfg_split, seed)
    ex = (df["temp_mean_c"] > cfg_split["extrapolation_temp_mean_c"]) | (df["age_h"] > cfg_split["extrapolation_age_h"])
    out = {}
    for name in ("train", "val", "test"):
        out[name] = df[df["lot_id"].isin(groups[name]) & ~ex]
    out["test_extrapolated"] = df[df["lot_id"].isin(groups["extrapolation"]) & ex]
    sets = {n: set(out[n]["lot_id"].unique()) for n in SPLITS}
    for i, a in enumerate(SPLITS):
        for b in SPLITS[i + 1:]:
            if sets[a] & sets[b]:
                raise AssertionError(f"lot leakage between {a} and {b}")
    manifest = {
        "seed": seed,
        "strategy": "group split by lot_id; extrapolation region held out",
        "fractions_of_lots": {k: cfg_split[k] for k in ("train", "val", "test", "extrapolation")},
        "extrapolation_rule": {
            "temp_mean_c_gt": cfg_split["extrapolation_temp_mean_c"],
            "age_h_gt": cfg_split["extrapolation_age_h"],
        },
        "rows": {n: len(out[n]) for n in SPLITS},
        "lots": {n: len(sets[n]) for n in SPLITS},
        "rows_dropped_in_extrapolation_region_from_train_val_test": int(
            (ex & df["lot_id"].isin(np.concatenate([groups[n] for n in ("train", "val", "test")]))).sum()),
        "lot_overlap": 0,
        "row_id_hash": sha256_json({n: out[n]["row_id"].tolist() for n in SPLITS}),
    }
    return out, manifest


def run(dataset: Path | str, config: Path | str | None = None, out_dir: Path | str | None = None) -> Path:
    cfg = load_config(config)
    df, meta = load_dataset(dataset)
    parts, manifest = split_dataframe(df, cfg["split"])
    manifest.update({"dataset_id": meta["dataset_id"], "dataset_hash": meta["dataset_hash"]})
    root = Path(out_dir) if out_dir else ARTIFACTS_DIR / "splits"
    folder = root / f"{meta['dataset_id']}-split-s{cfg['split']['seed']}"
    folder.mkdir(parents=True, exist_ok=True)
    for name, part in parts.items():
        part.to_parquet(folder / f"{name}.parquet", index=False)
    write_json(folder / "split_manifest.json", manifest)
    log.info("split -> %s rows=%s", folder, manifest["rows"])
    return folder


def load_split(folder: Path | str) -> dict[str, pd.DataFrame]:
    return {n: pd.read_parquet(Path(folder) / f"{n}.parquet") for n in SPLITS}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Split a dataset by lot")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(run(a.dataset, a.config, a.out))


if __name__ == "__main__":
    main()
