"""Adversarial contract tests for calibration, risk, recommendation and boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from salva_core import features
from salva_core.contracts import Lot, Market, Option, Shocks
from salva_core.loss_model import KineticLossModel
from salva_core.loss_model.lgbm_model import QUANTILES, LightGbmLossModel
from salva_core.params import ParamsError, load_product, load_products
from salva_core.recommendation import recommend
from salva_core.simulation import (
    SimulationEngine,
    analyze_parameter_sensitivity,
    analyze_sensitivity,
    draw,
    relative_hypothesis_parameter_paths,
)
from salva_core.simulation.engine import run_all


@pytest.fixture(scope="module")
def p():
    return load_product("tomato")


def test_reference_catalog_contains_operational_product_profiles():
    products = load_products()
    assert {"tomato", "banana_plantain", "mango", "avocado", "leafy_greens"} <= set(
        products
    )
    for code in ("banana_plantain", "mango", "avocado", "leafy_greens"):
        assert products[code].name == code
        assert products[code].k_ref > 0


class ConstantBooster:
    """Small stand-in for LightGBM; records the actual inference matrix."""

    def __init__(self, prediction: float) -> None:
        self.prediction = prediction
        self.last_matrix: np.ndarray | None = None

    def predict(self, matrix: np.ndarray, pred_contrib: bool = False) -> np.ndarray:
        self.last_matrix = np.array(matrix, copy=True)
        if pred_contrib:
            return np.zeros((len(matrix), matrix.shape[1] + 1))
        return np.full(len(matrix), self.prediction)


class AgeBooster:
    """Monotone fake whose P50 crosses the product's shelf-life threshold at 25 h."""

    def __init__(self, offset: float) -> None:
        self.offset = offset

    def predict(self, matrix: np.ndarray, pred_contrib: bool = False) -> np.ndarray:
        if pred_contrib:
            return np.zeros((len(matrix), matrix.shape[1] + 1))
        age = matrix[:, features.MODEL_COLUMNS.index("age_h")]
        return np.clip(age / 100.0 + self.offset, 0.0, 1.0)


def test_effective_temperature_shock_can_cross_range_without_aborting(p):
    f = features.assemble(
        p,
        maturity="breaker",
        packaging="crate",
        age_h=0.0,
        remaining_h=2.0,
        temp_air_c=49.5,
        temp_shock_c=np.array([-3.0, 0.0, 3.0]),
    )
    assert np.array_equal(f.temp_mean_c, np.array([46.5, 49.5, 52.5]))
    assert features.out_of_range_features(f, p) == ("temp_max_c", "temp_mean_c")


def test_lightgbm_clips_extrapolative_features_and_reports_them(p):
    f = features.assemble(
        p,
        maturity="breaker",
        packaging="crate",
        age_h=800.0,
        remaining_h=800.0,
        temp_air_c=49.5,
        temp_shock_c=4.0,
    )
    boosters = {q: ConstantBooster(q) for q in QUANTILES}
    model = LightGbmLossModel(boosters, p, "fake-lgbm")
    result = model.predict(f)
    assert result.extrapolated_features == (
        "age_h",
        "degree_hours_above_ref",
        "exposure_h",
        "remaining_transit_h",
        "temp_max_c",
        "temp_mean_c",
    )
    assert model.extrapolated_features(f) == result.extrapolated_features
    checked = [boosters[q].last_matrix for q in (0.10, 0.50, 0.90)]
    assert all(matrix is not None for matrix in checked)
    matrix = checked[1]
    assert matrix is not None
    for name, expected in (
        ("age_h", 168.0),
        ("remaining_transit_h", 144.0),
        ("temp_mean_c", 40.5),
        ("temp_max_c", 50.5),
        ("degree_hours_above_ref", 6396.0),
        ("exposure_h", 312.0),
    ):
        assert matrix[0, features.MODEL_COLUMNS.index(name)] == expected


def test_lightgbm_extrapolation_expands_outer_quantiles_and_preserves_median(p):
    f = features.assemble(
        p,
        maturity="breaker",
        packaging="crate",
        age_h=24.0,
        remaining_h=4.0,
        temp_air_c=45.0,
    )
    boosters = {q: ConstantBooster(q) for q in QUANTILES}
    model = LightGbmLossModel(boosters, p, "fake-lgbm")
    result = model.predict(f)
    assert "temp_mean_c" in result.extrapolated_features
    assert result.p10 == 0.0
    assert result.p50 == pytest.approx(0.50)
    assert result.p90 == 1.0
    sampled = model.sample_loss(f, np.array([0.10]))
    assert sampled[0] == 0.0


def test_chilling_penalty_is_applied_once_to_lightgbm_distribution(p):
    f = features.assemble(
        p,
        maturity="green",
        packaging="crate",
        age_h=336.0,
        remaining_h=0.0,
        temp_air_c=2.5,
    )
    from salva_core import kinetics

    injury = float(
        kinetics.chilling_loss_fraction_from_dose(
            kinetics.chilling_equivalent_exposure_h(f, p), "green", p
        )
    )
    boosters = {q: ConstantBooster(q) for q in QUANTILES}
    model = LightGbmLossModel(boosters, p, "fake-lgbm")
    adjusted = model.predict(f)
    expected_p50 = 1.0 - (1.0 - 0.50) * (1.0 - injury)
    assert adjusted.p50 == pytest.approx(expected_p50)
    assert adjusted.p10 <= adjusted.p50 <= adjusted.p90
    assert model.sample_loss(f, np.array([0.50]))[0] == pytest.approx(expected_p50)

    already_adjusted = LightGbmLossModel(
        {q: ConstantBooster(q) for q in QUANTILES},
        p,
        "fake-lgbm-chilled",
        metadata={"loss_includes_chilling_penalty": True},
    )
    assert already_adjusted.predict(f).p50 == pytest.approx(0.50)


def test_lightgbm_rejects_kinetic_parameter_sensitivity_without_retraining(p):
    model = LightGbmLossModel(
        {q: ConstantBooster(q) for q in QUANTILES}, p, "fake-lgbm"
    )
    lot = Lot(10.0, "breaker", "crate", 0.0, 4.0, 20.0)
    options = [Option("local", "continue", 10.0, Market(1, "local", 100.0, 100.0))]

    assert model.supports_parameter_sensitivity("product.t_ref_c")
    assert not model.supports_parameter_sensitivity("product.q10")
    model_paths = relative_hypothesis_parameter_paths(p, model=model)
    assert "product.t_ref_c" in model_paths
    assert "product.q10" not in model_paths
    with pytest.raises(
        ValueError, match="does not support parameter sensitivity.*product.q10"
    ):
        analyze_parameter_sensitivity(
            model,
            lot,
            options,
            p,
            draw(1_000, 5, market_ids=[1]),
            ["product.q10"],
        )


def test_lightgbm_loader_rejects_artifact_without_chilling_declaration(
    tmp_path: Path, p, monkeypatch
):
    (tmp_path / "metadata.json").write_text(
        json.dumps({"feature_schema_hash": features.schema_hash()}), encoding="utf-8"
    )

    import builtins

    original_import = builtins.__import__

    def import_without_joblib(name, *args, **kwargs):
        if name == "joblib":
            raise ModuleNotFoundError("joblib intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_joblib)
    with pytest.raises(ValueError, match="loss_includes_chilling_penalty"):
        LightGbmLossModel.load(tmp_path, p)


def test_lightgbm_artifact_ranges_override_planning_envelope(p):
    f = features.assemble(
        p,
        maturity="breaker",
        packaging="crate",
        age_h=24.0,
        remaining_h=4.0,
        temp_air_c=41.0,
    )
    boosters = {q: ConstantBooster(q) for q in QUANTILES}
    model = LightGbmLossModel(
        boosters,
        p,
        "artifact-ranged",
        metadata={"calibration_ranges": {"temp_mean_c": {"min": 10, "max": 42}}},
    )
    assert model.extrapolated_features(f) == ()
    f_outside = features.with_changes(f, p, temp_mean_c=43.0)
    assert model.extrapolated_features(f_outside) == ("temp_mean_c",)


@pytest.mark.parametrize(
    ("temp_c", "artifact_max", "expected_warnings"),
    [
        (41.0, 42.0, ()),
        (40.0, 39.0, ("temp_mean_c",)),
    ],
)
def test_scenario_warnings_follow_active_artifact_ranges(
    p, temp_c, artifact_max, expected_warnings
):
    lot = Lot(10.0, "breaker", "crate", 0.0, 0.0, temp_c)
    option = Option("continue", "continue", 10.0, Market(1, "Local", 100.0, 100.0))
    model = LightGbmLossModel(
        {q: ConstantBooster(q) for q in QUANTILES},
        p,
        "artifact-ranged",
        metadata={
            "calibration_ranges": {"temp_mean_c": {"min": 6.0, "max": artifact_max}}
        },
    )
    shocks = Shocks(
        temp=np.zeros(1_000),
        transit=np.ones(1_000),
        price=np.ones(1_000),
        absorb=np.ones(1_000),
        u=np.full(1_000, 0.5),
    )

    result = run_all(model, lot, [option], shocks, p, include_allocation=False)[0]

    assert result.extrapolation_warnings == expected_warnings


def test_lightgbm_rejects_malformed_artifact_calibration_ranges(p):
    boosters = {q: ConstantBooster(q) for q in QUANTILES}
    with pytest.raises(ValueError, match="min <= max"):
        LightGbmLossModel(
            boosters,
            p,
            "bad-range",
            metadata={"calibration_ranges": {"temp_mean_c": {"min": 45, "max": 10}}},
        )


def test_lightgbm_shelf_life_is_in_range_or_unknown(p):
    f = features.assemble(
        p,
        maturity="breaker",
        packaging="crate",
        age_h=10.0,
        remaining_h=8.0,
        temp_air_c=20.0,
    )
    model = LightGbmLossModel(
        {q: AgeBooster(q - 0.5) for q in QUANTILES}, p, "age-monotone"
    )
    assert model.remaining_shelf_life_p50_h(f) == pytest.approx(15.0, abs=0.1)
    outside = features.with_changes(f, p, temp_mean_c=45.0)
    assert model.remaining_shelf_life_p50_h(outside) is None


def test_scenario_reports_stochastic_extrapolation_instead_of_failing():
    params = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 0.0, 2.0, 49.5)
    option = Option("continue", "continue", 10.0, Market(1, "Local", 100.0, 100.0))
    result = SimulationEngine(KineticLossModel(params), params).run(
        lot, [option], n_draws=1_000, seed=9
    )[0]
    assert result.feasible
    assert "temp_mean_c" in result.extrapolation_warnings
    assert result.as_dict()["extrapolation_warnings"] == [
        "temp_max_c",
        "temp_mean_c",
    ]
    assert 0.0 <= result.loss_p10 <= 0.05
    assert 0.95 <= result.loss_p90 <= 1.0


def test_kinetic_extrapolation_widens_outer_quantiles_but_preserves_p50(p):
    f = features.assemble(
        p,
        maturity="breaker",
        packaging="crate",
        age_h=24.0,
        remaining_h=4.0,
        temp_air_c=45.0,
    )
    model = KineticLossModel(p)
    distribution = model.predict(f)
    assert distribution.p10 == 0.0
    assert distribution.p90 == 1.0
    expected_median = model._raw_sample_loss(f, 0.5)
    assert distribution.p50 == pytest.approx(expected_median)
    samples = model.sample_loss(f, np.array([0.1, 0.5, 0.9]))
    assert np.allclose(samples, [0.0, expected_median, 1.0])


def test_rm4_reason_survives_when_storage_is_also_infeasible():
    params = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 0.0, 1_000.0, 35.0)
    option = Option(
        "store-small",
        "store",
        5.0,
        Market(1, "Local", 100.0, 100.0),
        is_store=True,
        storage_mode="ambient_shade",
        storage_capacity_kg=5.0,
    )
    result = SimulationEngine(KineticLossModel(params), params).run(
        lot, [option], n_draws=1_000, seed=4
    )[0]
    assert not result.feasible
    assert result.infeasible_reason == "OPTION_CAPACITY_BELOW_LOT"
    assert result.discouraged
    assert result.discouraged_reason == "SHELF_LIFE_P50_EXCEEDED"


def test_recommendation_serializes_rm6_assumptions():
    params = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 2.0, 2.0, 22.0)
    option = Option("continue", "continue", 10.0, Market(1, "Local", 100.0, 100.0))
    results = SimulationEngine(KineticLossModel(params), params).run(
        lot, [option], n_draws=1_000, seed=8
    )
    payload = recommend(results).as_dict()
    assert payload["confidence"] in {"high", "medium", "low", "none"}
    assert "MODEL_BASED_ESTIMATE_NOT_GUARANTEE" in payload["assumptions"]
    assert "PRODUCT_PARAMETERS_REQUIRE_CALIBRATION" in payload["assumptions"]
    assert "MARKET_ABSORPTION_IS_AN_ASSUMPTION" in payload["assumptions"]


def test_sensitivity_axes_are_sorted_before_boundary_detection():
    params = load_product("tomato")
    model = KineticLossModel(params)
    lot = Lot(10.0, "breaker", "crate", 0.0, 4.0, 20.0)
    options = [
        Option("local", "sell_local", 10.0, Market(1, "Local", 100.0, 100.0)),
        Option(
            "regional",
            "reroute",
            10.0,
            Market(2, "Regional", 150.0, 100.0),
            extra_h=2.0,
        ),
    ]
    result = analyze_sensitivity(
        model,
        lot,
        options,
        params,
        temperatures_c=[35.0, 20.0],
        delays_h=[12.0, 0.0],
        n_draws=1_000,
        seed=3,
    )
    assert result.temperatures_c == (20.0, 35.0)
    assert result.delays_h == (0.0, 12.0)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda doc: doc["tomato"]["parameters"]["sigma_lot"].update(
                value=float("nan")
            ),
            "finite",
        ),
        (
            lambda doc: doc["tomato"]["valid_ranges"].update(
                temp_mean_c={"min": 40.0, "max": 10.0}
            ),
            "finite min <= max",
        ),
        (
            lambda doc: doc["tomato"]["calibration_ranges"].update(
                temp_mean_c={"min": 40.0, "max": 10.0}
            ),
            "finite min <= max",
        ),
        (
            lambda doc: doc["tomato"]["parameters"]["k_ref"].update(value=True),
            "boolean is not a numeric parameter",
        ),
        (
            lambda doc: doc["tomato"]["parameters"]["maturity"]["value"].pop("ripe"),
            "expected categories",
        ),
        (
            lambda doc: doc["tomato"]["parameters"]["chilling_threshold_c"][
                "value"
            ].pop("ripe"),
            "expected categories",
        ),
        (
            lambda doc: doc["tomato"]["parameters"][
                "chilling_temperature_scale_c"
            ].update(value=0.0),
            "chilling_temperature_scale_c must be > 0",
        ),
    ],
)
def test_product_configuration_rejects_invalid_numbers(tmp_path: Path, mutate, message):
    source = Path(__file__).parents[2] / "data/reference/products.yaml"
    doc = yaml.safe_load(source.read_text(encoding="utf-8"))
    mutate(doc)
    target = tmp_path / "products.yaml"
    target.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ParamsError, match=message):
        load_products(target)


def test_product_configuration_rejects_non_mapping_root(tmp_path: Path):
    target = tmp_path / "products.yaml"
    target.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ParamsError, match="root must be a mapping"):
        load_products(target)
