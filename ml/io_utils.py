"""Dataset IO with integrity checks (content hash stored in metadata.json)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def dataframe_hash(df: pd.DataFrame) -> str:
    """Deterministic content hash, independent of pandas/pyarrow versions and string dtype.

    Numeric columns are hashed as raw int64/float64 bytes, other columns as UTF-8 text.
    """
    h = hashlib.sha256()
    for col in df.columns:
        s = df[col]
        h.update(f"|{col}|".encode())
        if pd.api.types.is_bool_dtype(s) or pd.api.types.is_integer_dtype(s):
            h.update(b"int")
            h.update(np.ascontiguousarray(s.to_numpy(dtype=np.int64)).tobytes())
        elif pd.api.types.is_float_dtype(s):
            h.update(b"float")
            h.update(np.ascontiguousarray(s.to_numpy(dtype=np.float64)).tobytes())
        else:
            h.update(b"str")
            h.update("\x1f".join(s.astype(str).tolist()).encode("utf-8"))
    return h.hexdigest()


def save_dataset(
    df: pd.DataFrame, metadata: dict[str, Any], out_dir: Path | str
) -> Path:
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    df.to_parquet(folder / "dataset.parquet", index=False)
    (folder / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, default=str) + "\n"
    )
    return folder


def load_dataset(
    folder: Path | str, verify: bool = True
) -> tuple[pd.DataFrame, dict[str, Any]]:
    folder = Path(folder)
    df = pd.read_parquet(folder / "dataset.parquet")
    meta = json.loads((folder / "metadata.json").read_text())
    if verify and dataframe_hash(df) != meta["dataset_hash"]:
        raise ValueError(
            f"Dataset in {folder} does not match its recorded hash (corrupted or edited)"
        )
    return df, meta
