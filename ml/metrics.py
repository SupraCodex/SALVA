"""Metrics shared by baseline and candidate evaluation (all in loss-fraction units)."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
from salva_core import features as F
from salva_core.contracts import ConditionFeatures, LossModel
from salva_core.loss_model.lgbm_model import QUANTILES
from salva_core.params import ProductParams


def features_from_frame(df: pd.DataFrame, product: str = "tomato") -> ConditionFeatures:
    return F.from_arrays({c: df[c] for c in F.MODEL_COLUMNS}, product)


def mae(a, b) -> float:
    return float(np.mean(np.abs(np.asarray(a, float) - np.asarray(b, float))))


def pinball(y, pred, tau: float) -> float:
    d = np.asarray(y, float) - np.asarray(pred, float)
    return float(np.mean(np.maximum(tau * d, (tau - 1.0) * d)))


def coverage(y, lo, hi) -> float:
    y, lo, hi = (np.asarray(a, float) for a in (y, lo, hi))
    return float(np.mean((y >= lo) & (y <= hi)))


def distribution_metrics(model: LossModel, df: pd.DataFrame) -> dict[str, Any]:
    """Metrics of a model against REALISED synthetic losses of ``df``."""
    f = features_from_frame(df)
    y = df["loss"].to_numpy(float)
    d = model.predict(f)
    out = {
        "n_rows": len(df), "n_lots": int(df["lot_id"].nunique()),
        "mae_p50_vs_realised": mae(d.p50, y),
        "coverage_p10_p90": coverage(y, d.p10, d.p90),
        "quantile_order_violations": int(np.sum((d.p10 > d.p50 + 1e-12) | (d.p50 > d.p90 + 1e-12))),
        "pinball": {},
    }
    for q in QUANTILES:
        out["pinball"][f"{q:.2f}"] = pinball(y, model.sample_loss(f, q), q)
    out["pinball_mean"] = float(np.mean(list(out["pinball"].values())))
    return out


def fidelity_metrics(model: LossModel, reference: LossModel, df: pd.DataFrame) -> dict[str, float]:
    """Distance between ``model`` and the kinetic ``reference`` on identical features."""
    f = features_from_frame(df)
    a, b = model.predict(f), reference.predict(f)
    return {
        "mae_p10": mae(a.p10, b.p10), "mae_p50": mae(a.p50, b.p50), "mae_p90": mae(a.p90, b.p90),
        "max_abs_p50": float(np.max(np.abs(np.asarray(a.p50) - np.asarray(b.p50)))),
    }


def _sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    n = min(n, len(df))
    return df.sample(n=n, random_state=seed)


def monotonicity_violations(model: LossModel, params: ProductParams, df: pd.DataFrame,
                            cfg: dict[str, Any], seed: int = 0) -> dict[str, Any]:
    """Count cases where a worsening perturbation LOWERS P10, P50 or P90."""
    sub = _sample(df, int(cfg["n_rows"]), seed)
    f = features_from_frame(sub, params.name)
    tol = float(cfg["tolerance"])
    pert = cfg["perturbations"]
    amp = np.maximum(np.asarray(f.temp_max_c, float) - np.asarray(f.temp_mean_c, float), 0.0)
    order = list(params.maturity_order)
    mats = np.asarray(f.maturity, dtype=object)
    can_step = np.array([order.index(m) + pert["maturity_step"] < len(order) for m in mats])
    stepped = np.array([order[min(order.index(m) + pert["maturity_step"], len(order) - 1)] for m in mats], dtype=object)
    cases = {
        "temperature": F.with_changes(f, params, temp_mean_c=np.asarray(f.temp_mean_c) + pert["temp_mean_c_plus"]),
        "exposure_age": F.with_changes(f, params, age_h=np.asarray(f.age_h) + pert["exposure_plus_h"]),
        "transit": F.with_changes(
            f, params,
            remaining_transit_h=np.asarray(f.remaining_transit_h) + pert["transit_plus_h"],
            delay_h=np.minimum(np.asarray(f.delay_h), np.asarray(f.remaining_transit_h) + pert["transit_plus_h"]),
        ),
        "diurnal_amplitude": F.with_changes(f, params, diurnal_amp_c=amp + pert["diurnal_amp_plus_c"]),
        "maturity": F.with_changes(f, params, maturity=stepped),
    }
    base = model.predict(f)
    result: dict[str, Any] = {"n_rows": len(sub), "by_perturbation": {}}
    total = 0
    for name, cf in cases.items():
        new = model.predict(cf)
        mask = can_step if name == "maturity" else np.ones(len(sub), bool)
        v = 0
        for q in ("p10", "p50", "p90"):
            v += int(np.sum((np.asarray(getattr(new, q)) < np.asarray(getattr(base, q)) - tol) & mask))
        result["by_perturbation"][name] = v
        total += v
    result["total_violations"] = total
    return result


def latency_ms(model: LossModel, df: pd.DataFrame, n_rows: int, repeats: int) -> dict[str, float]:
    """Median wall time of predict() (P10/P50/P90) on ``n_rows`` rows, CPU, one process."""
    reps = int(np.ceil(n_rows / len(df)))
    big = pd.concat([df] * reps, ignore_index=True).iloc[:n_rows]
    f = features_from_frame(big)
    model.predict(f)                                          # warm-up
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        model.predict(f)
        times.append((time.perf_counter() - t0) * 1000.0)
    return {"n_rows": n_rows, "median_ms": float(np.median(times)), "max_ms": float(np.max(times))}


def pairwise_ordering_agreement(model: LossModel, reference: LossModel, params: ProductParams,
                                df: pd.DataFrame, n_pairs: int = 2000, seed: int = 0) -> dict[str, float]:
    """PROXY (informational): do both models rank two alternative conditions the same way?

    Two alternatives per row: a detour (extra hours) and a temperature change, drawn at
    random.  Pairs whose reference P50 differ by less than 0.01 are ignored.
    """
    rng = np.random.default_rng(seed)
    sub = _sample(df, n_pairs, seed)
    f = features_from_frame(sub, params.name)
    n = len(sub)

    def alt() -> ConditionFeatures:
        # remaining_transit_h is scaled by the hidden transit factor while delay_h is the
        # observed delay, so a few rows have delay > remaining; cap it for the variant.
        rem = np.asarray(f.remaining_transit_h) + rng.uniform(0, 24, n)
        return F.with_changes(
            f, params,
            remaining_transit_h=rem,
            delay_h=np.minimum(np.asarray(f.delay_h), rem),
            temp_mean_c=np.asarray(f.temp_mean_c) + rng.uniform(-4, 4, n),
        )

    a, b = alt(), alt()
    ref = np.asarray(reference.predict(a).p50) - np.asarray(reference.predict(b).p50)
    cand = np.asarray(model.predict(a).p50) - np.asarray(model.predict(b).p50)
    keep = np.abs(ref) > 0.01
    agree = float(np.mean(np.sign(ref[keep]) == np.sign(cand[keep]))) if keep.any() else float("nan")
    return {"agreement": agree, "pairs_used": int(keep.sum()), "pairs_total": int(n)}


def coverage_by_lot_ci(df: pd.DataFrame, lo, hi, n_boot: int = 500, seed: int = 0) -> dict[str, float]:
    """Coverage with a 95% interval from a bootstrap OVER LOTS (rows of a lot are correlated)."""
    hit = ((df["loss"].to_numpy(float) >= np.asarray(lo, float)) & (df["loss"].to_numpy(float) <= np.asarray(hi, float)))
    per_lot = pd.DataFrame({"lot": df["lot_id"].to_numpy(), "hit": hit}).groupby("lot")["hit"].agg(["sum", "count"])
    s, c = per_lot["sum"].to_numpy(float), per_lot["count"].to_numpy(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    boot = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    return {"coverage": float(s.sum() / c.sum()), "ci95_low": float(np.quantile(boot, 0.025)),
            "ci95_high": float(np.quantile(boot, 0.975)), "n_lots": len(s)}
