import copy

import numpy as np
import pytest
from salva_core.loss_model import KineticLossModel
from salva_core.params import load_product

from ml import decision_agreement as DA
from ml import evaluate, metrics, register
from ml.config import load_yaml


@pytest.fixture(scope="module")
def gate():
    return load_yaml(evaluate.GATE_PATH)


def passing_metrics():
    return {
        "fidelity_test": {"mae_p50": 0.01},
        "candidate_test": {"coverage_p10_p90": 0.80},
        "coverage_ci_test": {"ci95_low": 0.77, "ci95_high": 0.83},
        "baseline_test": {"coverage_p10_p90": 0.80},
        "monotonicity": {"total_violations": 0},
        "latency": {"median_ms": 100.0},
        "decision_agreement": {"status": "EVALUATED", "agreement": 0.92, "n_scenarios": 100},
    }


OK = {"status": "OK"}


def test_all_criteria_pass_gives_go(gate):
    assert evaluate.evaluate_go_nogo(passing_metrics(), gate, OK)["verdict"] == "LIGHTGBM GO"


@pytest.mark.parametrize("path,value", [
    (("fidelity_test", "mae_p50"), 0.05),
    (("candidate_test", "coverage_p10_p90"), 0.70),
    (("candidate_test", "coverage_p10_p90"), 0.90),
    (("monotonicity", "total_violations"), 1),
    (("latency", "median_ms"), 450.0),
])
def test_any_failed_criterion_gives_nogo(gate, path, value):
    m = passing_metrics()
    m[path[0]][path[1]] = value
    out = evaluate.evaluate_go_nogo(m, gate, OK)
    assert out["verdict"] == "LIGHTGBM NO-GO" and out["production_model"] == "KineticModel"


def test_low_decision_agreement_is_nogo(gate):
    m = passing_metrics()
    m["decision_agreement"]["agreement"] = 0.80
    assert evaluate.evaluate_go_nogo(m, gate, OK)["verdict"] == "LIGHTGBM NO-GO"


def test_unevaluated_decision_criterion_is_nogo(gate):
    m = passing_metrics()
    m["decision_agreement"] = {"status": "NOT_EVALUATED", "reason": "P1 engines not available yet"}
    out = evaluate.evaluate_go_nogo(m, gate, OK)
    assert out["verdict"] == "LIGHTGBM NO-GO" and any("NOT EVALUATED" in r for r in out["reasons"])


def test_thresholds_modified_after_commit_is_nogo(gate):
    out = evaluate.evaluate_go_nogo(passing_metrics(), gate, {"status": "MODIFIED_SINCE_COMMIT"})
    assert out["verdict"] == "LIGHTGBM NO-GO"


def test_threshold_boundaries_follow_the_registered_rules(gate):
    m = passing_metrics()
    m["fidelity_test"]["mae_p50"] = gate["criteria"]["p50_fidelity_mae"]["max"]          # strict <
    assert evaluate.evaluate_go_nogo(m, gate, OK)["verdict"] == "LIGHTGBM NO-GO"
    m = passing_metrics()
    m["candidate_test"]["coverage_p10_p90"] = gate["criteria"]["coverage_p10_p90"]["min"]  # inclusive
    assert evaluate.evaluate_go_nogo(m, gate, OK)["verdict"] == "LIGHTGBM GO"


def test_registered_thresholds_are_the_ones_of_the_brief(gate):
    c = gate["criteria"]
    assert c["p50_fidelity_mae"]["max"] == 0.03
    assert (c["coverage_p10_p90"]["min"], c["coverage_p10_p90"]["max"]) == (0.76, 0.84)
    assert c["monotonicity_violations"]["max"] == 0
    assert c["decision_agreement"]["min"] == 0.85
    assert c["latency_ms_10k_rows"]["max"] == 300


def test_git_integrity_reports_a_status():
    assert evaluate.git_integrity(evaluate.GATE_PATH)["status"] in {"OK", "MODIFIED_SINCE_COMMIT", "UNCOMMITTED", "UNKNOWN"}


def test_metric_primitives():
    y = np.array([0.0, 0.5, 1.0])
    assert metrics.mae(y, y) == 0.0
    assert metrics.pinball(y, y, 0.5) == 0.0
    assert metrics.pinball(np.array([1.0]), np.array([0.0]), 0.9) == pytest.approx(0.9)
    assert metrics.coverage(y, y - 0.1, y + 0.1) == 1.0
    assert metrics.coverage(y, y + 0.1, y + 0.2) == 0.0


def test_kinetic_model_has_zero_monotonicity_violations(small_split, gate):
    from ml.split import load_split

    p = load_product("tomato")
    out = metrics.monotonicity_violations(KineticLossModel(p), p, load_split(small_split)["test"], gate["monotonicity"])
    assert out["total_violations"] == 0 and out["n_rows"] > 0


def test_monotonicity_check_detects_a_broken_model(small_split, gate):
    from ml.split import load_split

    class Broken(KineticLossModel):
        def predict(self, f, *, with_factors=False):
            d = super().predict(f)
            from salva_core.contracts import LossDistribution

            flip = 1.0 - np.asarray(d.p50)         # decreases when conditions worsen
            return LossDistribution(flip, flip, flip)

    p = load_product("tomato")
    out = metrics.monotonicity_violations(Broken(p), p, load_split(small_split)["test"], copy.deepcopy(gate["monotonicity"]))
    assert out["total_violations"] > 0


def test_decision_agreement_with_injected_engine():
    p = load_product("tomato")
    k = KineticLossModel(p)
    same = DA.compute(k, k, p, n_scenarios=10, seed=1, decide=lambda m, sc: "continue")
    assert same["agreement"] == 1.0 and same["status"] == "EVALUATED"
    flip = {"n": 0}

    def alternating(model, scenario):
        flip["n"] += 1
        return "continue" if flip["n"] % 2 else "reroute"

    assert DA.compute(k, k, p, n_scenarios=10, seed=1, decide=alternating)["agreement"] == 0.0


def test_decision_agreement_uses_the_core_engines():
    p = load_product("tomato")
    k = KineticLossModel(p)
    out = DA.compute(k, k, p, n_scenarios=3, seed=1)
    assert out == {"status": "EVALUATED", "agreement": 1.0, "n_scenarios": 3}


def test_scenarios_are_deterministic_and_valid():
    p = load_product("tomato")
    a, b = DA.make_scenarios(p, 5, 3), DA.make_scenarios(p, 5, 3)
    assert a == b and all(len(opts) == 4 for _, opts in a)


def test_register_refuses_to_promote_without_go(tmp_path):
    rep = tmp_path / "rep"
    rep.mkdir()
    (rep / "go_nogo.json").write_text('{"go_nogo": {"verdict": "LIGHTGBM NO-GO"}}')
    pkg = tmp_path / "lgbm-x"
    pkg.mkdir()
    with pytest.raises(PermissionError):
        register.register(pkg, rep, promote=True, active_path=tmp_path / "active.json")
    cfg = register.register(pkg, rep, active_path=tmp_path / "active.json")
    assert cfg["production"] == "kinetic" and cfg["experimental"] == "lgbm-x"


def test_register_promotes_on_go(tmp_path):
    rep = tmp_path / "rep"
    rep.mkdir()
    (rep / "go_nogo.json").write_text('{"go_nogo": {"verdict": "LIGHTGBM GO"}}')
    pkg = tmp_path / "lgbm-y"
    pkg.mkdir()
    assert register.register(pkg, rep, promote=True, active_path=tmp_path / "a.json")["production"] == "lgbm-y"
