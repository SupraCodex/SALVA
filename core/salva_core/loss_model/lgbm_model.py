"""LightGBM quantile loss model (trained offline by ml/train.py, never inside the API)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ..contracts import ConditionFeatures, LossDistribution
from ..features import MODEL_COLUMNS, feature_schema, n_rows, schema_hash, to_matrix
from ..params import ProductParams, load_product
from .sampling import interp_quantiles, sort_and_clip

QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
_LEVELS = np.array(QUANTILES)
_IDX = {q: i for i, q in enumerate(QUANTILES)}


class QuantileBooster:
    """Picklable wrapper around a LightGBM Booster plus a constant initial score.

    LightGBM cannot combine its native quantile objective with monotone constraints, so
    ml/train.py trains monotone models with a custom pinball objective, which needs an
    explicit initial score (the empirical quantile of the training target).
    """

    def __init__(self, booster: Any, init: float = 0.0) -> None:
        self.booster = booster
        self.init = float(init)

    def predict(self, x: np.ndarray, pred_contrib: bool = False) -> np.ndarray:
        raw = np.asarray(self.booster.predict(x, pred_contrib=pred_contrib))
        if pred_contrib:
            raw = raw.copy()
            raw[:, -1] += self.init  # bias column
            return raw
        return raw + self.init


class ModelSchemaMismatch(ValueError):
    """The packaged model was trained with a different feature schema."""


class LightGbmLossModel:
    """LossModel backed by one LightGBM regressor per quantile.

    Quantile predictions are sorted per row (no crossing) and clipped to [0, 1].
    ``sample_loss(f, u)`` interpolates the 7-point quantile curve at ``u`` (flat tails
    below 5% and above 95%).
    """

    def __init__(
        self,
        models: dict[float, Any],
        params: ProductParams,
        version: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        missing = [q for q in QUANTILES if q not in models]
        if missing:
            raise ValueError(f"Missing quantile models: {missing}")
        self.models = models
        self.params = params
        self.version = version
        self.metadata = metadata or {}

    def _matrix(self, f: ConditionFeatures) -> tuple[np.ndarray, tuple[str, ...]]:
        """Encode and clip statistical-model inputs to documented calibration bounds."""
        x = to_matrix(f).copy()
        outside: list[str] = []
        for name, bounds in self.params.valid_ranges.items():
            if name not in MODEL_COLUMNS:
                continue
            index = MODEL_COLUMNS.index(name)
            values = x[:, index]
            if np.any((values < bounds["min"]) | (values > bounds["max"])):
                outside.append(name)
                x[:, index] = np.clip(values, bounds["min"], bounds["max"])
        return x, tuple(sorted(outside))

    def extrapolated_features(self, f: ConditionFeatures) -> tuple[str, ...]:
        """Names of calibration-bounded features that required clipping."""
        return self._matrix(f)[1]

    def quantile_matrix(self, f: ConditionFeatures) -> np.ndarray:
        x, _ = self._matrix(f)
        raw = np.column_stack([self.models[q].predict(x) for q in QUANTILES])
        return sort_and_clip(raw)

    def sample_loss(self, f: ConditionFeatures, u) -> np.ndarray:
        return interp_quantiles(self.quantile_matrix(f), _LEVELS, u)

    def predict(
        self, f: ConditionFeatures, *, with_factors: bool = False
    ) -> LossDistribution:
        # Only the three models needed for P10/P50/P90 are evaluated (the 5% and 95% models
        # cost about as much as the other five together); sorting enforces P10 <= P50 <= P90.
        x, extrapolated = self._matrix(f)
        q = sort_and_clip(
            np.column_stack([self.models[lv].predict(x) for lv in (0.10, 0.50, 0.90)])
        )
        p10, p50, p90 = q[:, 0], q[:, 1], q[:, 2]
        if n_rows(f) == 1:
            distribution = LossDistribution(
                p10=float(p10[0]),
                p50=float(p50[0]),
                p90=float(p90[0]),
                top_factors=None,
                extrapolated_features=extrapolated,
            )
        else:
            distribution = LossDistribution(
                p10=p10,
                p50=p50,
                p90=p90,
                top_factors=None,
                extrapolated_features=extrapolated,
            )
        factors = None
        if with_factors and n_rows(f) == 1:
            from .factors import explain

            factors = explain(self, f, self.params)
        return LossDistribution(
            p10=distribution.p10,
            p50=distribution.p50,
            p90=distribution.p90,
            top_factors=factors,
            extrapolated_features=extrapolated,
        )

    def shap_contributions(self, f: ConditionFeatures) -> np.ndarray:
        """Exact TreeSHAP values of the P50 model, shape (n_rows, n_features + 1).

        Last column is the bias.  Built into LightGBM (pred_contrib), no extra dependency.
        Raw per-feature values; user-facing factors come from factors.explain().
        """
        x, _ = self._matrix(f)
        return np.asarray(self.models[0.50].predict(x, pred_contrib=True))

    @classmethod
    def load(
        cls, path: str | Path, params: ProductParams | None = None
    ) -> LightGbmLossModel:
        import joblib

        folder = Path(path)
        meta = json.loads((folder / "metadata.json").read_text())
        if meta.get("feature_schema_hash") != schema_hash():
            raise ModelSchemaMismatch(
                f"Model trained with schema {meta.get('feature_schema_hash', '?')[:8]}, "
                f"code has {schema_hash()[:8]} (feature version {feature_schema()['version']})"
            )
        if list(meta.get("feature_columns", [])) != list(MODEL_COLUMNS):
            raise ModelSchemaMismatch(
                "Feature column order differs from the packaged model"
            )
        if params is not None and meta.get("product", "tomato") != params.name:
            raise ModelSchemaMismatch(
                f"Model product {meta.get('product', 'tomato')!r} does not match "
                f"requested product {params.name!r}"
            )
        models = joblib.load(folder / "models.joblib")
        return cls(
            models,
            params or load_product(meta.get("product", "tomato")),
            version=meta["model_version"],
            metadata=meta,
        )
