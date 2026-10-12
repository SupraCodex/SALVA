"""LossModel contract, P10<=P50<=P90, monotonicity in u, explanations, factory."""

import numpy as np
import pytest
from salva_core import features as F
from salva_core.contracts import LossModel
from salva_core.loss_model import KineticLossModel, get_loss_model
from salva_core.loss_model.factors import FACTOR_NAMES, contributions, explain
from salva_core.loss_model.sampling import interp_quantiles, sort_and_clip
from salva_core.params import load_product


@pytest.fixture(scope="module")
def p():
    return load_product("tomato")


@pytest.fixture(scope="module")
def model(p):
    return KineticLossModel(p)


def feats(p, **kw):
    args = {"maturity": "breaker", "packaging": "crate", "age_h": 50, "remaining_h": 18, "delay_h": 12, "temp_air_c": 29}
    args.update(kw)
    return F.assemble(p, **args)


def test_implements_contract(model):
    assert isinstance(model, LossModel) and model.version.startswith("kinetic-")


def test_quantile_order_and_bounds(p, model):
    rng = np.random.default_rng(1)
    n = 2000
    f = feats(p, age_h=rng.uniform(0, 168, n), remaining_h=rng.uniform(1, 72, n), delay_h=0.0,
              temp_air_c=rng.uniform(15, 38, n))
    d = model.predict(f)
    assert np.all(d.p10 <= d.p50) and np.all(d.p50 <= d.p90)
    assert np.all((d.p10 >= 0) & (d.p90 <= 1))


def test_loss_non_decreasing_in_u(p, model):
    f = feats(p)
    u = np.linspace(0.001, 0.999, 200)
    f_rep = feats(p, age_h=np.full(200, 50.0), temp_air_c=np.full(200, 29.0))
    loss = model.sample_loss(f_rep, u)
    assert np.all(np.diff(loss) >= -1e-12)
    assert f.exposure_h == 68.0


def test_predict_matches_sample_loss(p, model):
    f = feats(p)
    d = model.predict(f)
    assert d.p50 == pytest.approx(float(model.sample_loss(f, 0.5)))


def test_common_random_numbers_same_u_same_result(p, model):
    f = feats(p, temp_shock_c=np.zeros(5), transit_factor=np.ones(5))
    u = np.full(5, 0.3)
    assert np.allclose(model.sample_loss(f, u), model.sample_loss(f, u))


def test_explain_returns_quantified_factors(p, model):
    out = explain(model, feats(p), p)
    names = [n for n, _ in out]
    assert set(names) <= set(FACTOR_NAMES) and len(out) >= 2
    assert all(v > 0 for _, v in out)
    assert [v for _, v in out] == sorted((v for _, v in out), reverse=True)
    with_f = model.predict(feats(p), with_factors=True)
    assert with_f.top_factors == out


def test_delay_factor_zero_without_delay(p, model):
    contrib = contributions(model, feats(p, delay_h=0.0), p)
    assert float(contrib["delay"]) == pytest.approx(0.0)


def test_cooler_means_less_loss_in_explanations(p, model):
    hot = float(contributions(model, feats(p, temp_air_c=36), p)["temperature"])
    cool = float(contributions(model, feats(p, temp_air_c=21), p)["temperature"])
    assert hot > cool


def test_sampling_helpers():
    q = np.array([[0.3, 0.1, 0.2], [0.5, 0.6, 1.4]])
    s = sort_and_clip(q)
    assert np.all(np.diff(s, axis=1) >= 0) and s.max() <= 1.0
    levels = np.array([0.1, 0.5, 0.9])
    assert np.allclose(interp_quantiles(s, levels, 0.5), s[:, 1])
    assert np.allclose(interp_quantiles(s, levels, 0.3), 0.5 * (s[:, 0] + s[:, 1]))
    assert np.allclose(interp_quantiles(s, levels, 0.99), s[:, 2])      # flat tail


def test_factory_defaults_to_kinetic(tmp_path):
    m = get_loss_model(active_json=tmp_path / "missing.json")
    assert m.version.startswith("kinetic-")


def test_factory_falls_back_when_package_is_broken(tmp_path):
    cfg = tmp_path / "active.json"
    cfg.write_text('{"production": "lgbm-does-not-exist", "experimental": null}')
    assert get_loss_model(active_json=cfg).version.startswith("kinetic-")
