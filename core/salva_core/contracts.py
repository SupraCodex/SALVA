"""Shared data contracts between P1 (simulation), P2 (backend) and P3 (kinetics/ML).

PROPOSED by P3 because the file did not exist yet.  P1 must review it before merge
(see CONTRACT CHANGE notes in docs/p3-ml-kinetics.md).  Numeric feature fields accept a
float OR a NumPy array (one value per Monte Carlo draw / dataset row); all arrays that
appear together must broadcast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

Num = float | np.ndarray


@dataclass(frozen=True)
class Market:
    id: int
    name: str
    price: float  # FCFA / kg
    absorb_kg: float  # kg that the market absorbs at full price over the sale window


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
    extra_h: float = 0.0  # extra hours (detour or storage hold)
    temp_offset: float = 0.0  # degC; for storage use ProductParams.storage_offset(mode)
    cost: float = 0.0  # variable cost, FCFA per physical kg
    is_store: bool = False
    storage_mode: str = "none"
    storage_site_id: str | None = (
        None  # options sharing a site consume one capacity pool
    )
    storage_capacity_kg: float | None = None  # total physical capacity of that site


@dataclass(frozen=True)
class Shocks:
    """Random draws shared by ALL actions (common random numbers). Built by P1."""

    temp: np.ndarray  # additive temperature shock, degC
    transit: np.ndarray  # multiplicative factor on remaining+extra hours (lognormal)
    price: np.ndarray  # multiplicative price factor
    absorb: np.ndarray  # multiplicative absorption factor
    u: np.ndarray  # uniform(0,1) draws driving lot variability in the loss model


@dataclass(frozen=True)
class ConditionFeatures:
    """Derived conditions seen by a loss model. Produced ONLY by features.assemble/build.

    temp_mean_c is the EFFECTIVE mean PRODUCT temperature: air + packaging delta +
    storage offset + shock.  exposure_h = age_h + remaining_transit_h.
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


@runtime_checkable
class LossModel(Protocol):
    """What the simulation needs from any loss model (kinetic or LightGBM)."""

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
