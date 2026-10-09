"""Quantified risk factors, identical for every LossModel.

Method: one-at-a-time counterfactual.  For each factor we set it to a benign reference
and report how much the P50 loss fraction would drop.  Contributions are in loss-fraction
units (0.10 = 10 points of value), positive = the factor increases the loss.  They do not
add up exactly to the total (interactions), and they describe how the MODEL reasons, not
biological causality.  The backend passes these numbers to the LLM, which must not invent
any other factor.
"""

from __future__ import annotations

import numpy as np

from ..contracts import ConditionFeatures, LossModel
from ..features import n_rows, with_changes
from ..params import ProductParams

FACTOR_NAMES = (
    "temperature",
    "age",
    "transit",
    "delay",
    "maturity",
    "packaging",
    "storage",
)


def _benign_packaging(p: ProductParams) -> str:
    return min(p.pack_damage, key=lambda k: (p.pack_damage[k], p.pack_delta_c[k]))


def counterfactuals(
    f: ConditionFeatures, p: ProductParams
) -> dict[str, ConditionFeatures]:
    """Build one benign counterfactual per interpretable risk factor."""
    delay = np.asarray(f.delay_h, dtype=float)
    remaining = np.asarray(f.remaining_transit_h, dtype=float)
    delay_in_transit = np.minimum(delay, remaining)
    return {
        "temperature": with_changes(f, p, temp_mean_c=p.t_ref_c, diurnal_amp_c=0.0),
        "age": with_changes(f, p, age_h=0.0),
        "transit": with_changes(
            f,
            p,
            remaining_transit_h=delay_in_transit,
            delay_h=delay_in_transit,
        ),
        "delay": with_changes(
            f, p, remaining_transit_h=remaining - delay_in_transit, delay_h=0.0
        ),
        "maturity": with_changes(f, p, maturity=p.maturity_order[0]),
        "packaging": with_changes(f, p, packaging=_benign_packaging(p)),
        "storage": with_changes(f, p, hold_h=0.0, storage_mode="none"),
    }


def contributions(
    model: LossModel, f: ConditionFeatures, p: ProductParams
) -> dict[str, np.ndarray]:
    """P50-loss reduction obtained by neutralising each factor (array per row)."""
    base = np.asarray(model.predict(f).p50, dtype=float)
    out = {}
    for name, cf in counterfactuals(f, p).items():
        out[name] = base - np.asarray(model.predict(cf).p50, dtype=float)
    return out


def explain(
    model: LossModel,
    f: ConditionFeatures,
    p: ProductParams,
    top: int = 4,
    min_contribution: float = 1e-3,
) -> list[tuple[str, float]]:
    """Top factors for ONE row, sorted by decreasing contribution (loss-fraction units)."""
    if n_rows(f) != 1:
        raise ValueError(
            "explain() expects a single row; use contributions() for arrays"
        )
    contrib = {k: float(np.ravel(v)[0]) for k, v in contributions(model, f, p).items()}
    ranked = sorted(contrib.items(), key=lambda kv: kv[1], reverse=True)
    return [(k, v) for k, v in ranked if v >= min_contribution][:top]
