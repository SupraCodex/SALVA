import json
from pathlib import Path

import numpy as np
import pytest
from salva_core import features as F
from salva_core.contracts import LossModel
from salva_core.loss_model.lgbm_model import LightGbmLossModel, ModelSchemaMismatch

from ml import baseline, package, train
from ml.metrics import features_from_frame
from ml.split import load_split


@pytest.fixture(scope="module")
def run_dir(small_split, small_config, tmp_path_factory):
    return train.run(small_split, small_config, tmp_path_factory.mktemp("run") / "r")


def test_constraints_vector():
    mono = train.monotone_constraints()
    assert len(mono) == len(F.MODEL_COLUMNS)
    for col in ("temp_mean_c", "age_h", "exposure_h", "maturity", "temp_max_c"):
        assert mono[F.MODEL_COLUMNS.index(col)] == 1
    for col in ("packaging", "storage_mode"):
        assert mono[F.MODEL_COLUMNS.index(col)] == 0
    assert {F.MODEL_COLUMNS[i] for i in train.categorical_indices()} == {"packaging", "storage_mode"}


def test_baseline_written_before_training(small_split, run_dir):
    assert (small_split / "baseline_metrics.json").exists()
    b = json.loads((small_split / "baseline_metrics.json").read_text())
    assert b["real_world_validation"] == "NOT PERFORMED" and b["monotonicity"]["total_violations"] == 0


def test_training_log_is_complete(run_dir):
    log = json.loads((run_dir / "train_log.json").read_text())
    for key in ("seed", "dataset_hash", "hyperparameters", "feature_schema_hash", "dependencies", "per_quantile", "mode"):
        assert key in log
    assert log["DATA_TYPE"] == "SYNTHETIC"


def test_model_loads_and_follows_contract(run_dir, small_split):
    from ml.evaluate import load_candidate

    model = load_candidate(run_dir)
    assert isinstance(model, LossModel)
    f = features_from_frame(load_split(small_split)["test"].head(200))
    d = model.predict(f)
    assert np.all(d.p10 <= d.p50 + 1e-12) and np.all(d.p50 <= d.p90 + 1e-12)
    assert np.all((d.p10 >= 0) & (d.p90 <= 1))
    u = np.linspace(0.01, 0.99, 200)
    rep = F.assemble(model.params, maturity="breaker", packaging="crate", age_h=np.full(200, 40.0),
                     remaining_h=np.full(200, 20.0), temp_air_c=np.full(200, 28.0))
    loss = model.sample_loss(rep, u)
    assert np.all(np.diff(loss) >= -1e-12)


def test_predictions_are_reproducible(small_split, small_config, run_dir, tmp_path):
    from ml.evaluate import load_candidate

    again = train.run(small_split, small_config, tmp_path / "again", skip_baseline=True)
    f = features_from_frame(load_split(small_split)["test"].head(300))
    a, b = load_candidate(run_dir).predict(f), load_candidate(again).predict(f)
    assert np.array_equal(a.p50, b.p50) and np.array_equal(a.p90, b.p90)


def test_package_roundtrip_and_schema_check(small_split, run_dir, small_config, tmp_path):
    from ml import evaluate

    gate = tmp_path / "gate.yaml"
    import yaml

    g = yaml.safe_load(evaluate.GATE_PATH.read_text())
    g["monotonicity"]["n_rows"] = 200
    g["latency"].update({"n_rows": 500, "repeats": 2})
    g["decision_agreement"]["n_scenarios"] = 5
    gate.write_text(yaml.safe_dump(g))
    rep = evaluate.evaluate(run_dir, small_split, small_config, gate_path=gate)
    report_dir = Path(tmp_path / "rep")
    report_dir.mkdir()
    (report_dir / "metrics.json").write_text(json.dumps(rep, default=str))
    pkg = package.package(run_dir, report_dir, tmp_path / "pkgs")
    model = LightGbmLossModel.load(pkg)
    assert model.version == rep["model_version"]
    meta = json.loads((pkg / "metadata.json").read_text())
    meta["feature_schema_hash"] = "0" * 64
    (pkg / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ModelSchemaMismatch):
        LightGbmLossModel.load(pkg)


def test_forbidden_columns_cannot_reach_the_matrix(small_split):
    df = load_split(small_split)["train"]
    mat = train.make_matrix(df.head(50), "tomato")
    assert mat.shape[1] == len(F.MODEL_COLUMNS)


def test_unknown_mode_rejected():
    x = np.zeros((10, len(F.MODEL_COLUMNS)))
    with pytest.raises(ValueError):
        train.fit_quantile_models(x, np.zeros(10), x, np.zeros(10), {"mode": "magic"})


def test_baseline_module_standalone(small_split):
    path = baseline.run(small_split)
    assert path.exists()
