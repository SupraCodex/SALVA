"""Dataset IO with integrity checks (content hash stored in metadata.json)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def dataframe_hash(df: pd.DataFrame) -> str:
    """Deterministic content hash (column names, dtypes and values; not the parquet bytes)."""
    h = hashlib.sha256()
    for col in df.columns:
        h.update(str(col).encode())
        h.update(str(df[col].dtype).encode())
        h.update(pd.util.hash_pandas_object(df[col], index=False).to_numpy().tobytes())
    return h.hexdigest()


def save_dataset(df: pd.DataFrame, metadata: dict[str, Any], out_dir: Path | str) -> Path:
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    df.to_parquet(folder / "dataset.parquet", index=False)
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True, default=str) + "\n")
    return folder


def load_dataset(folder: Path | str, verify: bool = True) -> tuple[pd.DataFrame, dict[str, Any]]:
    folder = Path(folder)
    df = pd.read_parquet(folder / "dataset.parquet")
    meta = json.loads((folder / "metadata.json").read_text())
    if verify and dataframe_hash(df) != meta["dataset_hash"]:
        raise ValueError(f"Dataset in {folder} does not match its recorded hash (corrupted or edited)")
    return df, meta
