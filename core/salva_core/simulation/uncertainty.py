"""Reproducible Monte Carlo shocks shared by every candidate action."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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


def draw(
    n: int = DEFAULT_DRAWS,
    seed: int = 42,
    *,
    market_ids: Iterable[int] = (),
) -> Shocks:
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
    ids = _market_ids(market_ids)
    u = rng.random(size)
    eps = np.finfo(float).eps
    u = np.clip(u, eps, 1.0 - eps)
    temp = rng.normal(0.0, TEMPERATURE_SIGMA_C, size)
    transit = rng.lognormal(0.0, TRANSIT_LOG_SIGMA, size)
    price = rng.lognormal(0.0, PRICE_LOG_SIGMA, size)
    absorb = rng.lognormal(0.0, ABSORPTION_LOG_SIGMA, size)
    return Shocks(
        temp=temp,
        transit=transit,
        price=price,
        absorb=absorb,
        u=u,
        price_by_market={
            market_id: rng.lognormal(0.0, PRICE_LOG_SIGMA, size) for market_id in ids
        },
        absorb_by_market={
            market_id: rng.lognormal(0.0, ABSORPTION_LOG_SIGMA, size)
            for market_id in ids
        },
    )


def _market_ids(market_ids: Iterable[int]) -> tuple[int, ...]:
    """Validate and canonically order market ids for deterministic independent draws."""
    try:
        ids = tuple(market_ids)
    except TypeError as exc:
        raise ShockValidationError(
            "market_ids must be an iterable of integers"
        ) from exc
    if any(isinstance(value, bool) or not isinstance(value, Integral) for value in ids):
        raise ShockValidationError("market_ids must contain only integer ids")
    if len(set(ids)) != len(ids):
        raise ShockValidationError("market_ids must be unique")
    return tuple(sorted(int(value) for value in ids))


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
    market_arrays: dict[str, dict[int, np.ndarray] | None] = {}
    for name in ("price_by_market", "absorb_by_market"):
        raw = getattr(shocks, name, None)
        if raw is None:
            market_arrays[name] = None
            continue
        if not isinstance(raw, Mapping):
            raise ShockValidationError(f"shocks.{name} must be a mapping by market id")
        checked: dict[int, np.ndarray] = {}
        for market_id, values in raw.items():
            if isinstance(market_id, bool) or not isinstance(market_id, Integral):
                raise ShockValidationError(
                    f"shocks.{name} keys must be integer market ids"
                )
            try:
                arr = np.asarray(values, dtype=float)
            except (TypeError, ValueError) as exc:
                raise ShockValidationError(
                    f"shocks.{name}[{market_id}] must be a numeric vector"
                ) from exc
            if arr.ndim != 1 or arr.size != actual_n:
                raise ShockValidationError(
                    f"shocks.{name}[{market_id}] must have shape ({actual_n},)"
                )
            if not np.all(np.isfinite(arr)) or np.any(arr <= 0):
                raise ShockValidationError(
                    f"shocks.{name}[{market_id}] must contain finite positive multipliers"
                )
            checked[int(market_id)] = arr
        market_arrays[name] = checked
    return Shocks(
        temp=arrays["temp"],
        transit=arrays["transit"],
        price=arrays["price"],
        absorb=arrays["absorb"],
        u=arrays["u"],
        price_by_market=market_arrays["price_by_market"],
        absorb_by_market=market_arrays["absorb_by_market"],
    )
