"""Adversarial contract tests for calibration, risk, recommendation and boundaries."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from salva_core import features
from salva_core.contracts import Lot, Market, Option
from salva_core.loss_model import KineticLossModel
from salva_core.loss_model.lgbm_model import QUANTILES, LightGbmLossModel
from salva_core.params import ParamsError, load_product, load_products
from salva_core.recommendation import recommend
from salva_core.simulation import SimulationEngine, analyze_sensitivity


@pytest.fixture(scope="module")
def p():
    return load_product("tomato")


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


def test_effective_temperature_shock_can_cross_range_without_aborting(p):
    f = features.assemble(
        p,
        maturity="breaker",
        packaging="crate",
        age_h=2.0,
        remaining_h=2.0,
        temp_air_c=49.5,
        temp_shock_c=np.array([-3.0, 0.0, 3.0]),
    )
    assert np.array_equal(f.temp_mean_c, np.array([46.5, 49.5, 52.5]))
    assert features.out_of_range_features(f, p) == ("temp_mean_c",)


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
        "remaining_transit_h",
        "temp_mean_c",
    )
    assert model.extrapolated_features(f) == result.extrapolated_features
    checked = [boosters[q].last_matrix for q in (0.10, 0.50, 0.90)]
    assert all(matrix is not None for matrix in checked)
    matrix = checked[1]
    assert matrix is not None
    for name, expected in (
        ("age_h", 720.0),
        ("remaining_transit_h", 720.0),
        ("temp_mean_c", 50.0),
    ):
        assert matrix[0, features.MODEL_COLUMNS.index(name)] == expected


def test_scenario_reports_stochastic_extrapolation_instead_of_failing():
    params = load_product("tomato")
    lot = Lot(10.0, "breaker", "crate", 0.0, 2.0, 49.5)
    option = Option("continue", "continue", 10.0, Market(1, "Local", 100.0, 100.0))
    result = SimulationEngine(KineticLossModel(params), params).run(
        lot, [option], n_draws=1_000, seed=9
    )[0]
    assert result.feasible
    assert "temp_mean_c" in result.extrapolation_warnings
    assert result.as_dict()["extrapolation_warnings"] == ["temp_mean_c"]


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
            lambda doc: doc["tomato"]["parameters"]["k_ref"].update(value=True),
            "boolean is not a numeric parameter",
        ),
        (
            lambda doc: doc["tomato"]["parameters"]["maturity"]["value"].pop("ripe"),
            "expected categories",
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
