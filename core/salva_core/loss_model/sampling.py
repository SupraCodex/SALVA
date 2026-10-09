"""Quantile-function helpers shared by quantile-based loss models."""

from __future__ import annotations

import numpy as np


def sort_and_clip(q_matrix: np.ndarray) -> np.ndarray:
    """Make each row a valid quantile curve: within [0, 1] and non-decreasing.

    Independently trained quantile models can cross; sorting each row (monotone
    rearrangement) guarantees P10 <= P50 <= P90.
    """
    return np.sort(np.clip(q_matrix, 0.0, 1.0), axis=1)


def interp_quantiles(q_matrix: np.ndarray, levels: np.ndarray, u: np.ndarray | float) -> np.ndarray:
    """Per-row linear interpolation of a quantile curve at probability ``u``.

    ``q_matrix`` has shape (N, K) with sorted rows, ``levels`` (K,) the probability of each
    column.  ``u`` outside [levels[0], levels[-1]] is clamped: tails are flat (a documented
    simplification: the model has no information beyond its extreme quantiles).
    """
    n, k = q_matrix.shape
    uu = np.broadcast_to(np.asarray(u, dtype=float), (n,))
    uu = np.clip(uu, levels[0], levels[-1])
    idx = np.clip(np.searchsorted(levels, uu, side="right") - 1, 0, k - 2)
    lo, hi = levels[idx], levels[idx + 1]
    w = (uu - lo) / (hi - lo)
    rows = np.arange(n)
    return q_matrix[rows, idx] * (1.0 - w) + q_matrix[rows, idx + 1] * w
