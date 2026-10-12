"""Package a trained model so that P2 (backend) can load it without any ML code.

    python -m ml.package --run ml/artifacts/runs/<version> --report ml/reports/<version>

Output: ml/artifacts/models/<version>/{models.joblib, metadata.json}.  Loading:
    LightGbmLossModel.load(folder)   (verifies the feature-schema hash)
No dependency on FastAPI.  The package is data about an EXPERIMENTAL or production model;
which one is used in production is decided only by ml/register.py after a GO verdict.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from salva_core import features as F
from salva_core.params import repo_root

from .config import ARTIFACTS_DIR, write_json


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo_root()), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def package(run_dir: Path | str, report_dir: Path | str, out_root: Path | str | None = None) -> Path:
    run_dir, report_dir = Path(run_dir), Path(report_dir)
    log = json.loads((run_dir / "train_log.json").read_text())
    report = json.loads((report_dir / "metrics.json").read_text())
    if report["model_version"] != log["model_version"]:
        raise ValueError("report and run belong to different model versions")
    folder = Path(out_root or ARTIFACTS_DIR / "models") / log["model_version"]
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_dir / "models.joblib", folder / "models.joblib")
    meta: dict[str, Any] = {
        "model_version": log["model_version"],
        "model_type": "lightgbm-quantile",
        "loss_model_contract": "salva_core.contracts.LossModel",
        "quantiles": [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95],
        "product": "tomato",
        "DATA_TYPE": "SYNTHETIC",
        "real_world_validation": "NOT PERFORMED",
        "dataset_id": log["dataset_id"], "dataset_hash": log["dataset_hash"],
        "seed": log["seed"], "train_mode": log.get("mode"),
        "hyperparameters": log["hyperparameters"],
        "products_yaml_sha256": log["products_yaml_sha256"],
        "feature_version": F.FEATURE_VERSION, "feature_schema_hash": F.schema_hash(),
        "feature_columns": list(F.MODEL_COLUMNS), "feature_schema": F.feature_schema(),
        "metrics": {k: report["metrics"][k] for k in ("fidelity_test", "candidate_test", "monotonicity", "latency", "decision_agreement")},
        "go_nogo": report["go_nogo"]["verdict"],
        "go_nogo_reasons": report["go_nogo"]["reasons"],
        "thresholds_sha256": report["thresholds_sha256"],
        "dependencies": log["dependencies"],
        "git_commit": _git_commit(),
        "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    write_json(folder / "metadata.json", meta)
    return folder


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Package a trained model for loading by the backend")
    ap.add_argument("--run", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    print(package(a.run, a.report, a.out))


if __name__ == "__main__":
    main()
