import numpy as np
import pandas as pd
import pytest
from salva_core import features as F
from salva_core.params import load_product

from ml import generate
from ml.config import load_config
from ml.io_utils import dataframe_hash, load_dataset


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def params():
    return load_product("tomato")


def make(cfg, params, seed=1, n_lots=30, rows=20):
    return generate.generate_dataset(cfg, params, n_lots=n_lots, rows_per_lot=rows, seed=seed)


def test_same_seed_same_dataset(cfg, params):
    assert dataframe_hash(make(cfg, params, 5)) == dataframe_hash(make(cfg, params, 5))


def test_different_seed_different_dataset(cfg, params):
    assert dataframe_hash(make(cfg, params, 5)) != dataframe_hash(make(cfg, params, 6))


def test_size_and_ids(cfg, params):
    df = make(cfg, params, n_lots=30, rows=20)
    assert len(df) == 600 and df["lot_id"].nunique() == 30 and df["row_id"].is_unique
    assert (df.groupby("lot_id").size() == 20).all()


def test_no_nan_inf_and_bounds(cfg, params):
    df = make(cfg, params, n_lots=100, rows=20)
    num = df.select_dtypes("number")
    assert np.isfinite(num.to_numpy()).all()
    assert df["loss"].between(0, 1).all()
    assert df["hidden_mean_quality"].between(0, 1, inclusive="right").all() and (df["hidden_mean_quality"] > 0).all()
    assert (df["age_h"] >= 0).all() and (df["remaining_transit_h"] >= 0).all()


def test_hidden_columns_are_not_features():
    assert not set(generate.HIDDEN_COLUMNS) & set(F.MODEL_COLUMNS)
    assert generate.TARGET not in F.MODEL_COLUMNS


def test_lot_rows_share_lot_level_attributes(cfg, params):
    df = make(cfg, params)
    g = df.groupby("lot_id")
    assert (g["maturity"].nunique() == 1).all() and (g["packaging"].nunique() == 1).all()
    assert (g["hidden_u"].nunique() == 1).all()


def test_all_categories_covered(cfg, params):
    df = make(cfg, params, n_lots=300, rows=20)
    assert set(df["maturity"]) == set(params.maturity)
    assert set(df["packaging"]) == set(params.pack_delta_c)
    assert set(df["storage_mode"]) == set(params.storage_temp_offset_c)


def test_metadata_traceability(small_dataset):
    df, meta = load_dataset(small_dataset)
    assert meta["DATA_TYPE"] == "SYNTHETIC" and meta["GENERATOR"] == "KINETIC MODEL"
    for key in ("SEED", "VERSION", "dataset_hash", "products_yaml_sha256", "config_sha256", "feature_schema_hash"):
        assert key in meta
    assert meta["n_rows"] == len(df)


def test_tampering_is_detected(small_dataset, tmp_path):
    import shutil

    copy = tmp_path / "ds"
    shutil.copytree(small_dataset, copy)
    df, _ = load_dataset(copy)
    df.loc[0, "loss"] = 0.123
    df.to_parquet(copy / "dataset.parquet", index=False)
    with pytest.raises(ValueError, match="hash"):
        load_dataset(copy)


def test_invalid_sizes_rejected(cfg, params):
    with pytest.raises(ValueError):
        generate.generate_dataset(cfg, params, n_lots=0, rows_per_lot=5, seed=1)


def test_hash_is_independent_of_string_storage_and_dtype_width():
    a = pd.DataFrame({"x": [1.0, 2.5], "n": [1, 2], "s": ["a", "b"]})
    b = a.astype({"s": "string", "n": "int32"})
    assert dataframe_hash(a) == dataframe_hash(b)
    assert dataframe_hash(a) != dataframe_hash(a.assign(x=[1.0, 2.6]))
