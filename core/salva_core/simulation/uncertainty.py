"""Reproducible Monte Carlo shocks shared by every candidate action."""

from __future__ import annotations

from numbers import Integral

import numpy as np

from ..contracts import Shocks

DEFAULT_DRAWS = 2_000
MIN_DRAWS = 100
MAX_DRAWS = 20_000
TEMPERATURE_SIGMA_C = 1.5
TRANSIT_LOG_SIGMA = 0.2
PRICE_LOG_SIGMA = 0.12
ABSORPTION_LOG_SIGMA = 0.25


class ShockValidationError(ValueError):
    """Raised when a caller supplies malformed random draws."""


def draw(n: int = DEFAULT_DRAWS, seed: int = 42) -> Shocks:
    """Draw common random numbers for a run.

    Lognormal multipliers are parameterized as ``LogNormal(0, sigma)``: their median is
    one, matching the design specification. The same vector is intentionally reused by
    every action. ``u`` is kept strictly inside (0, 1) for inverse-normal quantile models.
    """
    if (
        isinstance(n, bool)
        or not isinstance(n, Integral)
        or not MIN_DRAWS <= int(n) <= MAX_DRAWS
    ):
        raise ShockValidationError(
            f"n must be an integer in [{MIN_DRAWS}, {MAX_DRAWS}]"
        )
    if isinstance(seed, bool) or not isinstance(seed, Integral) or int(seed) < 0:
        raise ShockValidationError("seed must be a non-negative integer")

    rng = np.random.default_rng(int(seed))
    size = int(n)
    u = rng.random(size)
    eps = np.finfo(float).eps
    u = np.clip(u, eps, 1.0 - eps)
    return Shocks(
        temp=rng.normal(0.0, TEMPERATURE_SIGMA_C, size),
        transit=rng.lognormal(0.0, TRANSIT_LOG_SIGMA, size),
        price=rng.lognormal(0.0, PRICE_LOG_SIGMA, size),
        absorb=rng.lognormal(0.0, ABSORPTION_LOG_SIGMA, size),
        u=u,
    )


def validate(shocks: Shocks, n: int | None = None) -> Shocks:
    """Validate and normalize a supplied ``Shocks`` bundle without changing its draws."""
    names = ("temp", "transit", "price", "absorb", "u")
    arrays: dict[str, np.ndarray] = {}
    lengths: set[int] = set()
    for name in names:
        try:
            arr = np.asarray(getattr(shocks, name), dtype=float)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ShockValidationError(
                f"shocks.{name} must be a numeric vector"
            ) from exc
        if arr.ndim != 1 or arr.size == 0:
            raise ShockValidationError(f"shocks.{name} must be a non-empty 1-D vector")
        if not np.all(np.isfinite(arr)):
            raise ShockValidationError(f"shocks.{name} must contain only finite values")
        arrays[name] = arr
        lengths.add(arr.size)
    if len(lengths) != 1:
        raise ShockValidationError(
            "all shock vectors must have the same number of draws"
        )
    actual_n = lengths.pop()
    if n is not None and actual_n != n:
        raise ShockValidationError(f"expected {n} draws, received {actual_n}")
    for name in ("transit", "price", "absorb"):
        if np.any(arrays[name] <= 0):
            raise ShockValidationError(f"shocks.{name} multipliers must be > 0")
    if np.any((arrays["u"] < 0) | (arrays["u"] > 1)):
        raise ShockValidationError("shocks.u must be in [0, 1]")
    return Shocks(**arrays)
