"""Evaluation of LightGBM against the kinetic baseline and the PRE-REGISTERED go/no-go.

    python -m ml.evaluate --run ml/artifacts/runs/<version> --split ml/artifacts/splits/<dir>

Thresholds live in ml/params/go_nogo.yaml, committed before any model existed.  This
script records their sha256 and flags the verdict if the file was modified since its
commit.  NO-GO is a valid result: the kinetic model then stays the production model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from salva_core import features as F
from salva_core.loss_model.kinetic_model import KineticLossModel
from salva_core.loss_model.lgbm_model import LightGbmLossModel
from salva_core.params import load_product, repo_root

from . import decision_agreement as DA
from . import metrics as M
from .config import REPORTS_DIR, load_config, load_yaml, sha256_file, write_json
from .split import load_split

GATE_PATH = Path(__file__).parent / "params" / "go_nogo.yaml"
EVALUATOR_VERSION = "1.0.0"


def git_integrity(path: Path) -> dict[str, Any]:
    """Was the thresholds file committed, and is the working copy unchanged?"""
    root = repo_root()

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )

    try:
        rel = str(path.resolve().relative_to(root.resolve()))
        first = git("log", "--diff-filter=A", "--format=%H %cI", "--", rel)
        if first.returncode != 0 or not first.stdout.strip():
            return {"status": "UNCOMMITTED", "detail": "thresholds file has no commit"}
        modified = git("diff", "--quiet", "HEAD", "--", rel).returncode != 0
        return {
            "status": "MODIFIED_SINCE_COMMIT" if modified else "OK",
            "first_commit": first.stdout.strip().splitlines()[-1],
        }
    except (OSError, ValueError):
        return {"status": "UNKNOWN", "detail": "git not available"}


def load_candidate(run_dir: Path) -> LightGbmLossModel:
    log = json.loads((run_dir / "train_log.json").read_text())
    models = joblib.load(run_dir / "models.joblib")
    return LightGbmLossModel(
        models, load_product(), version=log["model_version"], metadata=log
    )


def shap_importance(
    model: LightGbmLossModel, df, n: int = 2000, seed: int = 0
) -> dict[str, float]:
    sub = df.sample(n=min(n, len(df)), random_state=seed)
    contrib = model.shap_contributions(M.features_from_frame(sub))[:, :-1]
    mean_abs = np.mean(np.abs(contrib), axis=0)
    total = float(mean_abs.sum()) or 1.0
    return {c: float(v / total) for c, v in zip(F.MODEL_COLUMNS, mean_abs, strict=True)}


def evaluate_go_nogo(
    m: dict[str, Any], gate: dict[str, Any], integrity: dict[str, Any]
) -> dict[str, Any]:
    c = gate["criteria"]
    res: dict[str, Any] = {}

    def add(
        name: str, value: float | None, passed: bool, rule: str, note: str = ""
    ) -> None:
        res[name] = {"value": value, "rule": rule, "passed": bool(passed), "note": note}

    v = m["fidelity_test"]["mae_p50"]
    add(
        "p50_fidelity_mae",
        v,
        v < c["p50_fidelity_mae"]["max"],
        f"< {c['p50_fidelity_mae']['max']}",
    )
    v = m["candidate_test"]["coverage_p10_p90"]
    lo, hi = c["coverage_p10_p90"]["min"], c["coverage_p10_p90"]["max"]
    ci = m["coverage_ci_test"]
    add(
        "coverage_p10_p90",
        v,
        lo <= v <= hi,
        f"in [{lo}, {hi}]",
        f"95% CI over lots [{ci['ci95_low']:.3f}, {ci['ci95_high']:.3f}]; "
        f"kinetic reference (perfect model) = {m['baseline_test']['coverage_p10_p90']:.3f}",
    )
    v = m["monotonicity"]["total_violations"]
    add(
        "monotonicity_violations",
        v,
        v <= c["monotonicity_violations"]["max"],
        f"<= {c['monotonicity_violations']['max']}",
    )
    d = m["decision_agreement"]
    if d["status"] == "EVALUATED":
        add(
            "decision_agreement",
            d["agreement"],
            d["agreement"] >= c["decision_agreement"]["min"],
            f">= {c['decision_agreement']['min']}",
        )
    else:
        add(
            "decision_agreement",
            None,
            False,
            f">= {c['decision_agreement']['min']}",
            f"NOT EVALUATED: {d.get('reason', 'unknown')}",
        )
    v = m["latency"]["median_ms"]
    add(
        "latency_ms_10k_rows",
        v,
        v < c["latency_ms_10k_rows"]["max"],
        f"< {c['latency_ms_10k_rows']['max']} ms",
    )

    failed = [k for k, r in res.items() if not r["passed"]]
    reasons = [
        f"{k}: {res[k]['value']} (required {res[k]['rule']}) {res[k]['note']}".strip()
        for k in failed
    ]
    if integrity["status"] not in ("OK", "UNKNOWN"):
        reasons.append(f"integrity: thresholds file status = {integrity['status']}")
    go = not failed and integrity["status"] in ("OK", "UNKNOWN")
    return {
        "verdict": "LIGHTGBM GO" if go else "LIGHTGBM NO-GO",
        "criteria": res,
        "reasons": reasons or ["all pre-registered criteria satisfied"],
        "production_model": "LightGBM (candidate)" if go else "KineticModel",
        "experimental_model": None if go else "LightGBM",
    }


def evaluate(
    run_dir: Path | str,
    split_dir: Path | str,
    config: Path | str | None = None,
    *,
    decide: DA.DecisionFn | None = None,
    gate_path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_config(config)
    gate_path = gate_path or GATE_PATH
    gate = load_yaml(gate_path)
    params = load_product(cfg["product"])
    run_dir, split_dir = Path(run_dir), Path(split_dir)
    splits = load_split(split_dir)
    cand = load_candidate(run_dir)
    kin = KineticLossModel(params)
    log = json.loads((run_dir / "train_log.json").read_text())

    test, extra = splits["test"], splits["test_extrapolated"]
    f_test = M.features_from_frame(test)
    d_test = cand.predict(f_test)
    try:
        dec = DA.compute(
            kin,
            cand,
            params,
            n_scenarios=gate["decision_agreement"]["n_scenarios"],
            seed=gate["decision_agreement"]["seed"],
            decide=decide,
        )
    except DA.DecisionUnavailable as exc:
        dec = {"status": "NOT_EVALUATED", "reason": str(exc)}

    m: dict[str, Any] = {
        "evaluator_version": EVALUATOR_VERSION,
        "fidelity_test": M.fidelity_metrics(cand, kin, test),
        "fidelity_extrapolated": M.fidelity_metrics(cand, kin, extra),
        "candidate_test": M.distribution_metrics(cand, test),
        "candidate_val": M.distribution_metrics(cand, splits["val"]),
        "candidate_extrapolated": M.distribution_metrics(cand, extra),
        "baseline_test": M.distribution_metrics(kin, test),
        "baseline_extrapolated": M.distribution_metrics(kin, extra),
        "coverage_ci_test": M.coverage_by_lot_ci(test, d_test.p10, d_test.p90),
        "monotonicity": M.monotonicity_violations(
            cand, params, test, gate["monotonicity"]
        ),
        "monotonicity_baseline": M.monotonicity_violations(
            kin, params, test, gate["monotonicity"]
        ),
        "latency": M.latency_ms(
            cand, test, gate["latency"]["n_rows"], gate["latency"]["repeats"]
        ),
        "latency_baseline": M.latency_ms(
            kin, test, gate["latency"]["n_rows"], gate["latency"]["repeats"]
        ),
        "pairwise_ordering_proxy": M.pairwise_ordering_agreement(
            cand, kin, params, test
        ),
        "decision_agreement": dec,
        "shap_importance_p50": shap_importance(cand, test),
    }
    integrity = git_integrity(gate_path)
    verdict = evaluate_go_nogo(m, gate, integrity)
    return {
        "model_version": cand.version,
        "dataset_id": log["dataset_id"],
        "dataset_hash": log["dataset_hash"],
        "seed": log["seed"],
        "train_mode": log.get("mode"),
        "data_type": "SYNTHETIC",
        "real_world_validation": "NOT PERFORMED",
        "thresholds_sha256": sha256_file(gate_path),
        "thresholds_integrity": integrity,
        "metrics": m,
        "go_nogo": verdict,
    }


def render_report(r: dict[str, Any]) -> str:
    m, g = r["metrics"], r["go_nogo"]
    c = g["criteria"]

    def mark(k: str) -> str:
        return "PASS" if c[k]["passed"] else "FAIL"

    def val(k: str, fmt: str = ".4f") -> str:
        v = c[k]["value"]
        return "n/a" if v is None else format(v, fmt)

    b, t = m["baseline_test"], m["candidate_test"]
    lines = [
        f"Model: LightGBM ({r['model_version']}, {r['train_mode']})",
        f"Dataset version: {r['dataset_id']}  (hash {r['dataset_hash'][:12]})",
        f"Seed: {r['seed']}",
        "DATA TYPE: SYNTHETIC (labels from the kinetic model). Real-world validation: NOT PERFORMED.",
        "",
        f"P50 MAE (fidelity to kinetic, test): {val('p50_fidelity_mae')}  [{mark('p50_fidelity_mae')}]  required {c['p50_fidelity_mae']['rule']}",
        f"P10-P90 coverage (test): {val('coverage_p10_p90', '.3f')}  [{mark('coverage_p10_p90')}]  required {c['coverage_p10_p90']['rule']}",
        f"  {c['coverage_p10_p90']['note']}",
        f"Monotonicity violations: {val('monotonicity_violations', '.0f')}  [{mark('monotonicity_violations')}]  required {c['monotonicity_violations']['rule']}",
        f"Recommendation agreement: {val('decision_agreement', '.3f')}  [{mark('decision_agreement')}]  required {c['decision_agreement']['rule']}",
        f"  {c['decision_agreement']['note']}".rstrip(),
        f"Latency (10k rows, median): {val('latency_ms_10k_rows', '.1f')} ms  [{mark('latency_ms_10k_rows')}]  required {c['latency_ms_10k_rows']['rule']}",
        "",
        f"GO/NO-GO: {g['verdict']}",
        "Reason:",
        *[f"  - {x}" for x in g["reasons"]],
        f"Production model: {g['production_model']}   Experimental model: {g['experimental_model']}",
        f"Thresholds file sha256: {r['thresholds_sha256'][:16]}...  integrity: {r['thresholds_integrity']['status']}",
        "",
        "How good is the kinetic baseline? (labels include irreducible lot variability)",
        f"  kinetic: P50 MAE vs realised {b['mae_p50_vs_realised']:.4f} | coverage {b['coverage_p10_p90']:.3f} | mean pinball {b['pinball_mean']:.5f}",
        f"  LightGBM: P50 MAE vs realised {t['mae_p50_vs_realised']:.4f} | coverage {t['coverage_p10_p90']:.3f} | mean pinball {t['pinball_mean']:.5f}",
        "",
        "Extrapolation set (temperature > 34 or age > 96 h; reported, NOT part of the verdict)",
        (
            f"  fidelity P50 MAE {m['fidelity_extrapolated']['mae_p50']:.4f} (max {m['fidelity_extrapolated']['max_abs_p50']:.3f}) | "
            f"coverage {m['candidate_extrapolated']['coverage_p10_p90']:.3f} | kinetic coverage {m['baseline_extrapolated']['coverage_p10_p90']:.3f}"
        ),
        "",
        (
            f"Pairwise ordering proxy (informational): agreement {m['pairwise_ordering_proxy']['agreement']:.3f} "
            f"on {m['pairwise_ordering_proxy']['pairs_used']} pairs"
        ),
        "Global SHAP importance of the P50 model (share): "
        + ", ".join(
            f"{k}={v:.2f}"
            for k, v in sorted(m["shap_importance_p50"].items(), key=lambda kv: -kv[1])[
                :5
            ]
        ),
    ]
    return "\n".join(lines) + "\n"


def run(
    run_dir: Path | str,
    split_dir: Path | str,
    config: Path | str | None = None,
    out_dir: Path | str | None = None,
) -> Path:
    r = evaluate(run_dir, split_dir, config)
    folder = Path(out_dir) if out_dir else REPORTS_DIR / r["model_version"]
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / "metrics.json", r)
    write_json(
        folder / "go_nogo.json",
        {
            k: r[k]
            for k in (
                "model_version",
                "dataset_id",
                "seed",
                "go_nogo",
                "thresholds_sha256",
            )
        },
    )
    (folder / "report.md").write_text(render_report(r))
    return folder


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Evaluate LightGBM vs kinetic baseline and decide GO/NO-GO"
    )
    ap.add_argument("--run", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    folder = run(a.run, a.split, a.config, a.out)
    print((folder / "report.md").read_text())
    print(f"reports -> {folder}")


if __name__ == "__main__":
    main()
