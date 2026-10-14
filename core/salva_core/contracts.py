"""Shared data contracts between P1 (simulation), P2 (backend) and P3 (kinetics/ML).

PROPOSED by P3 because the file did not exist yet.  P1 must review it before merge
(see CONTRACT CHANGE notes in docs/p3-ml-kinetics.md).  Numeric feature fields accept a
float OR a NumPy array (one value per Monte Carlo draw / dataset row); all arrays that
appear together must broadcast.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

Num = float | np.ndarray


@dataclass(frozen=True)
class Market:
    id: int
    name: str
    price: float  # FCFA / kg
    absorb_kg: float  # full-price kg over the sale window; caller resolves defaults


@dataclass(frozen=True)
class Lot:
    """State of a lot at analysis time (what the user knows)."""

    kg: float
    maturity: str  # green | breaker | ripe
    packaging: str  # crate | carton | sack
    age_h: float  # hours since harvest
    remaining_h: float  # hours until planned arrival (INCLUDES any delay)
    temp_c: float  # mean AIR temperature expected on the way (degC)
    product: str = "tomato"
    delay_h: float = 0.0  # current delay vs plan, already inside remaining_h
    diurnal_amp_c: float | None = (
        None  # half amplitude of daily cycle; None -> product default
    )


@dataclass(frozen=True)
class Option:
    """One candidate action evaluated by the simulation engine."""

    id: str
    action: str  # continue | store | reroute | sell_local
    kg: float  # maximum physical kg this route can handle
    market: Market
    extra_h: float = 0.0  # extra transit/detour hours; legacy store values mean hold_h
    temp_offset: float | None = (
        None  # degC override; None uses the product mode default
    )
    cost: float = 0.0  # variable cost, FCFA per physical kg
    is_store: bool = False
    storage_mode: str = "none"
    storage_site_id: str | None = (
        None  # options sharing a site consume one capacity pool
    )
    storage_capacity_kg: float | None = (
        None  # free physical capacity available to this run
    )
    hold_h: float | None = (
        None  # storage duration; None preserves legacy store semantics
    )
    storage_cost_fcfa_kg_day: float = 0.0  # storage tariff, FCFA per physical kg-day
    transport_distance_km: float = 0.0
    transport_cost_fcfa_kg_km: float = 0.0
    transit_saving_h: float = (
        0.0  # planned transit avoided (closer market); never cuts the delay
    )


@dataclass(frozen=True)
class Shocks:
    """Common action draws plus optional market-specific economic random factors."""

    temp: np.ndarray  # additive temperature shock, degC
    transit: np.ndarray  # multiplicative factor on remaining+extra hours (lognormal)
    price: np.ndarray  # multiplicative price factor
    absorb: np.ndarray  # multiplicative absorption factor
    u: np.ndarray  # uniform(0,1) draws driving lot variability in the loss model
    price_by_market: Mapping[int, np.ndarray] | None = None
    absorb_by_market: Mapping[int, np.ndarray] | None = None


@dataclass(frozen=True)
class ConditionFeatures:
    """Derived conditions seen by a loss model. Produced ONLY by features.assemble/build.

    Temperature features summarize the air/packaging conditions over historical exposure,
    transit, and storage. The storage offset applies only during ``hold_h``. The optional
    phase fields retain the exact Q10 exposure used by the kinetic model and are not model
    matrix columns.
    """

    product: str
    maturity: str | np.ndarray
    packaging: str | np.ndarray
    storage_mode: str | np.ndarray
    age_h: Num
    temp_mean_c: Num
    temp_max_c: Num
    degree_hours_above_ref: Num
    remaining_transit_h: Num
    delay_h: Num
    exposure_h: Num
    hold_h: Num = 0.0
    thermal_rate_factor: Num | None = field(default=None, repr=False, compare=False)
    historical_rate_factor: Num | None = field(default=None, repr=False, compare=False)
    future_rate_factor: Num | None = field(default=None, repr=False, compare=False)
    history_temp_mean_c: Num | None = field(default=None, repr=False, compare=False)
    transit_temp_mean_c: Num | None = field(default=None, repr=False, compare=False)
    storage_temp_mean_c: Num | None = field(default=None, repr=False, compare=False)
    diurnal_amp_c: Num | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class LossDistribution:
    """Uncertainty of the value-loss fraction of a lot. P10 <= P50 <= P90, all in [0, 1].

    The three quantiles describe ONE predictive distribution (lot-to-lot variability at
    fixed conditions); they are not three independent predictions.
    """

    p10: Num
    p50: Num
    p90: Num
    top_factors: list[tuple[str, float]] | None = field(default=None)
    extrapolated_features: tuple[str, ...] = ()


@runtime_checkable
class LossModel(Protocol):
    """What the simulation needs from any loss model (kinetic or LightGBM).

    Models may additionally expose ``remaining_shelf_life_p50_h(features)``. This optional
    capability is intentionally discovered at runtime; it returns remaining hours or None
    when a calibrated P50 threshold crossing cannot be supported, rather than extrapolating.
    """

    version: str

    def predict(
        self, f: ConditionFeatures, *, with_factors: bool = False
    ) -> LossDistribution:
        """P10/P50/P90 of the loss fraction for each feature row."""

    def sample_loss(self, f: ConditionFeatures, u: np.ndarray) -> np.ndarray:
        """Loss fraction in [0,1] for uniform draws ``u`` (quantile function of the loss).

        Monotone non-decreasing in ``u``.  Pass the SAME ``u`` for every action
        (common random numbers).
        """
