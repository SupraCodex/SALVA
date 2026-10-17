import numpy as np
import pytest
from salva_core import features as F
from salva_core.params import load_product

from ml import generate
from ml.config import load_config
from ml.validate import assert_no_forbidden_features, validate_dataframe


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def params():
    return load_product("tomato")


@pytest.fixture()
def df(cfg, params):
    return generate.generate_dataset(cfg, params, n_lots=60, rows_per_lot=20, seed=3)


def test_clean_dataset_passes(df, cfg, params):
    rep = validate_dataframe(df, params, cfg)
    assert rep.ok, rep.to_text()
    assert rep.stats["max_label_recompute_error"] == 0.0


def test_nan_is_an_error(df, cfg, params):
    df.loc[3, "age_h"] = np.nan
    assert not validate_dataframe(df, params, cfg).ok


def test_infinity_is_an_error(df, cfg, params):
    df.loc[3, "temp_mean_c"] = np.inf
    assert any("infinity" in e for e in validate_dataframe(df, params, cfg).errors)


def test_loss_out_of_bounds(df, cfg, params):
    df.loc[0, "loss"] = 1.2
    assert any(
        "outside [0, 1]" in e for e in validate_dataframe(df, params, cfg).errors
    )


def test_negative_age(df, cfg, params):
    df.loc[0, "age_h"] = -1.0
    assert not validate_dataframe(df, params, cfg).ok


def test_unknown_category(df, cfg, params):
    df.loc[0, "packaging"] = "bag"
    assert any("packaging" in e for e in validate_dataframe(df, params, cfg).errors)


def test_label_not_matching_equations_is_detected(df, cfg, params):
    df.loc[5, "loss"] = (
        min(df.loc[5, "loss"] + 0.05, 1.0)
        if df.loc[5, "loss"] < 0.9
        else df.loc[5, "loss"] - 0.05
    )
    assert any("kinetics.py" in e for e in validate_dataframe(df, params, cfg).errors)


def test_inconsistent_exposure(df, cfg, params):
    df.loc[0, "exposure_h"] += 10
    assert any("exposure_h" in e for e in validate_dataframe(df, params, cfg).errors)


def test_missing_columns(df, cfg, params):
    assert not validate_dataframe(df.drop(columns=["temp_max_c"]), params, cfg).ok


def test_forbidden_feature_guard():
    assert_no_forbidden_features(list(F.MODEL_COLUMNS))
    with pytest.raises(ValueError, match="leakage"):
        assert_no_forbidden_features([*F.MODEL_COLUMNS, "hidden_u"])
    with pytest.raises(ValueError):
        assert_no_forbidden_features([*F.MODEL_COLUMNS, "loss"])
