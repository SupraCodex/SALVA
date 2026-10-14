"""Recommendation materiality and confidence threshold validation."""

import pytest
from salva_core.recommendation import Policy


@pytest.mark.parametrize(
    "kw",
    [
        {"lam": -0.1},
        {"lam": 1.1},
        {"materiality": 1.1},
        {"high_probability": 0.2, "medium_probability": 0.4},
        {"reference_value_fcfa": 0},
        {"long_detour_threshold_h": -1},
    ],
)
def test_invalid_policy_thresholds_are_rejected(kw):
    with pytest.raises(ValueError):
        Policy(**kw)
