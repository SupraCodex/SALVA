"""Dataset validation (P3): impossible values, NaN/inf, categories, consistency, leakage.

    python -m ml.validate --dataset ml/artifacts/datasets/<dataset_id>

Exit code 1 if any ERROR is found.  The check "labels reproduce from kinetics.py" proves
the dataset was produced by the single, current implementation of the equations.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from salva_core import features as F
from salva_core import kinetics
from salva_core.loss_model.kinetic_model import KineticLossModel
from salva_core.params import ProductParams, load_product

from .config import load_config, write_json
from .generate import HIDDEN_COLUMNS, TARGET
from .io_utils import load_dataset


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_text(self) -> str:
        lines = [(f"VALIDATION: {'OK' if self.ok else 'FAILED'} "
                 f"({len(self.errors)} error(s), {len(self.warnings)} warning(s))")]
        lines += [f"  ERROR   {e}" for e in self.errors]
        lines += [f"  WARNING {w}" for w in self.warnings]
        lines += [f"  stat    {k}: {v}" for k, v in self.stats.items()]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "stats": self.stats}


def assert_no_forbidden_features(columns: list[str] | tuple[str, ...]) -> None:
    """Hidden generator variables must never be model inputs (data leakage)."""
    bad = sorted(set(columns) & (set(HIDDEN_COLUMNS) | {TARGET}))
    bad += [c for c in columns if c.startswith("hidden_") and c not in bad]
    if bad:
        raise ValueError(f"Forbidden feature columns (leakage): {bad}")


def validate_dataframe(df: pd.DataFrame, params: ProductParams, cfg: dict[str, Any]) -> ValidationReport:
    rep = ValidationReport()
    v = cfg.get("validation", {})
    required = ["lot_id", "row_id", TARGET, *F.MODEL_COLUMNS]
    missing = [c for c in required if c not in df.columns]
    if missing:
        rep.errors.append(f"missing columns: {missing}")
        return rep
    try:
        assert_no_forbidden_features(list(F.MODEL_COLUMNS))
    except ValueError as exc:
        rep.errors.append(str(exc))
    if len(df) == 0:
        rep.errors.append("empty dataset")
        return rep

    num_cols = [c for c in (*F.NUMERIC_FEATURES, TARGET, *[h for h in HIDDEN_COLUMNS if h in df]) if c in df]
    for c in num_cols:
        a = df[c].to_numpy(dtype=float)
        if np.isnan(a).any():
            rep.errors.append(f"{c}: contains NaN")
        if np.isinf(a).any():
            rep.errors.append(f"{c}: contains infinity")
    if rep.errors:
        return rep

    if df["row_id"].duplicated().any():
        rep.errors.append("row_id is not unique")
    loss = df[TARGET].to_numpy(float)
    if (loss < 0).any() or (loss > 1).any():
        rep.errors.append(f"{TARGET} outside [0, 1]: min={loss.min():.4g} max={loss.max():.4g}")
    if "hidden_mean_quality" in df:
        q = df["hidden_mean_quality"].to_numpy(float)
        if (q <= 0).any() or (q > 1).any():
            rep.errors.append("hidden_mean_quality outside (0, 1]")
    for c in ("age_h", "remaining_transit_h", "delay_h", "exposure_h", "degree_hours_above_ref"):
        if (df[c].to_numpy(float) < 0).any():
            rep.errors.append(f"{c}: negative values")
    age, rem, _delay, expo = (df[c].to_numpy(float) for c in ("age_h", "remaining_transit_h", "delay_h", "exposure_h"))
    if not np.allclose(expo, age + rem, atol=1e-6):
        rep.errors.append("exposure_h != age_h + remaining_transit_h")
    t_mean, t_max = df["temp_mean_c"].to_numpy(float), df["temp_max_c"].to_numpy(float)
    if (t_max < t_mean - 1e-9).any():
        rep.errors.append("temp_max_c < temp_mean_c")
    if (t_mean < -20).any() or (t_mean > 60).any():
        rep.errors.append("temp_mean_c outside the physically plausible range [-20, 60] degC")
    dh = np.maximum(t_mean - params.t_ref_c, 0.0) * expo
    if not np.allclose(df["degree_hours_above_ref"].to_numpy(float), dh, rtol=1e-6, atol=1e-6):
        rep.errors.append("degree_hours_above_ref inconsistent with temp_mean_c and exposure_h")

    for col, allowed in (("maturity", params.maturity), ("packaging", params.pack_delta_c),
                         ("storage_mode", params.storage_temp_offset_c)):
        bad = set(df[col].astype(str).unique()) - set(allowed)
        if bad:
            rep.errors.append(f"{col}: unknown values {sorted(bad)}")
    if rep.errors:
        return rep

    # labels must be reproducible from the single implementation of the equations
    if "hidden_u" in df:
        f = F.from_arrays({c: df[c] for c in F.MODEL_COLUMNS}, params.name)
        recomputed = KineticLossModel(params).sample_loss(f, df["hidden_u"].to_numpy(float))
        err = float(np.max(np.abs(recomputed - loss)))
        rep.stats["max_label_recompute_error"] = err
        if err > 1e-9:
            rep.errors.append(f"labels do not match kinetics.py (max abs diff {err:.3g})")
        _ = kinetics  # imported to make the dependency explicit
    else:
        rep.warnings.append("hidden_u absent: label reproducibility not checked")

    # distributions
    rep.stats.update({
        "rows": len(df), "lots": int(df["lot_id"].nunique()),
        "loss_mean": round(float(loss.mean()), 4), "loss_p10": round(float(np.quantile(loss, 0.1)), 4),
        "loss_p90": round(float(np.quantile(loss, 0.9)), 4),
        "share_loss_gt_0.99": round(float((loss > 0.99).mean()), 4),
        "temp_mean_range": [round(float(t_mean.min()), 2), round(float(t_mean.max()), 2)],
        "exposure_h_range": [round(float(expo.min()), 2), round(float(expo.max()), 2)],
    })
    if not v.get("min_loss_mean", 0.0) <= loss.mean() <= v.get("max_loss_mean", 1.0):
        rep.warnings.append(f"mean loss {loss.mean():.3f} outside the expected range")
    if (loss > 0.99).mean() > 0.5:
        rep.warnings.append("more than half of the rows are saturated (loss > 0.99)")
    min_rows = int(v.get("min_rows_per_category", 0))
    for col in F.CATEGORICAL_FEATURES:
        counts = df[col].astype(str).value_counts()
        rep.stats[f"count_{col}"] = {k: int(c) for k, c in counts.items()}
        for k, c in counts.items():
            if c < min_rows:
                rep.warnings.append(f"{col}={k}: only {c} rows (< {min_rows})")
    return rep


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Validate a synthetic dataset")
    ap.add_argument("--dataset", required=True, help="dataset folder (dataset.parquet + metadata.json)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--report", default=None, help="write the report as JSON")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    df, meta = load_dataset(a.dataset)
    rep = validate_dataframe(df, load_product(cfg["product"]), cfg)
    print(rep.to_text())
    out = a.report or str(Path(a.dataset) / "validation_report.json")
    write_json(out, {**rep.to_dict(), "dataset_id": meta["dataset_id"]})
    sys.exit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
