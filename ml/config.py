"""Typed access to ml/params/*.yaml and shared helpers (hashing, paths)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from salva_core.params import repo_root

ML_DIR = repo_root() / "ml"
PARAMS_DIR = ML_DIR / "params"
ARTIFACTS_DIR = ML_DIR / "artifacts"
REPORTS_DIR = ML_DIR / "reports"


def load_yaml(path: Path | str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    return load_yaml(path or PARAMS_DIR / "tomato.yaml")


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_json(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def write_json(path: Path | str, obj: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")
