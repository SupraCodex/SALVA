import numpy as np
import pytest

from ml import split
from ml.config import load_config
from ml.io_utils import load_dataset


@pytest.fixture(scope="module")
def cfg_split():
    return load_config()["split"]


def test_no_lot_in_two_splits(small_dataset, cfg_split):
    df, _ = load_dataset(small_dataset)
    parts, manifest = split.split_dataframe(df, cfg_split)
    sets = [set(p["lot_id"]) for p in parts.values()]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            assert not sets[i] & sets[j]
    assert manifest["lot_overlap"] == 0


def test_extrapolation_region_isolated(small_dataset, cfg_split):
    df, _ = load_dataset(small_dataset)
    parts, _ = split.split_dataframe(df, cfg_split)
    for name in ("train", "val", "test"):
        p = parts[name]
        assert (p["temp_mean_c"] <= cfg_split["extrapolation_temp_mean_c"]).all()
        assert (p["age_h"] <= cfg_split["extrapolation_age_h"]).all()
    e = parts["test_extrapolated"]
    ex = (e["temp_mean_c"] > cfg_split["extrapolation_temp_mean_c"]) | (e["age_h"] > cfg_split["extrapolation_age_h"])
    assert ex.all() and len(e) > 0


def test_reproducible(small_dataset, cfg_split):
    df, _ = load_dataset(small_dataset)
    a, ma = split.split_dataframe(df, cfg_split)
    b, mb = split.split_dataframe(df, cfg_split)
    assert ma["row_id_hash"] == mb["row_id_hash"]
    assert a["train"]["row_id"].tolist() == b["train"]["row_id"].tolist()


def test_seed_changes_assignment(small_dataset, cfg_split):
    df, _ = load_dataset(small_dataset)
    _, m1 = split.split_dataframe(df, cfg_split)
    _, m2 = split.split_dataframe(df, {**cfg_split, "seed": cfg_split["seed"] + 1})
    assert m1["row_id_hash"] != m2["row_id_hash"]


def test_fraction_validation():
    with pytest.raises(ValueError):
        split.assign_lots(np.arange(100), {"train": 0.5, "val": 0.2, "test": 0.2, "extrapolation": 0.2}, 1)
    with pytest.raises(ValueError):
        split.assign_lots(np.arange(3), {"train": 0.65, "val": 0.125, "test": 0.125, "extrapolation": 0.1}, 1)


def test_every_group_has_lots():
    g = split.assign_lots(np.arange(10), {"train": 0.65, "val": 0.125, "test": 0.125, "extrapolation": 0.1}, 1)
    assert all(len(v) >= 1 for v in g.values()) and sum(len(v) for v in g.values()) == 10


def test_saved_split_loads(small_split):
    parts = split.load_split(small_split)
    assert set(parts) == set(split.SPLITS) and len(parts["train"]) > 0
