"""Test fixtures: make the repo root importable and share one small synthetic pipeline."""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml import generate, split
from ml.config import load_config


@pytest.fixture(scope="session")
def small_config(tmp_path_factory):
    """Tomato config shrunk for speed (same structure, small data, few trees)."""
    cfg = load_config()
    cfg["generator"].update({"n_lots": 120, "rows_per_lot": 25})
    cfg["lightgbm"].update({"n_estimators": 60, "early_stopping_rounds": 20})
    path = tmp_path_factory.mktemp("cfg") / "tomato_small.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path


@pytest.fixture(scope="session")
def small_dataset(small_config, tmp_path_factory):
    out = tmp_path_factory.mktemp("datasets")
    return generate.run(small_config, out_dir=out)


@pytest.fixture(scope="session")
def small_split(small_config, small_dataset, tmp_path_factory):
    out = tmp_path_factory.mktemp("splits")
    return split.run(small_dataset, small_config, out_dir=out)
