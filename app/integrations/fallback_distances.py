"""Road distances from data/reference/distances.csv (no routing API in wave 1). Symmetric lookup."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings


@dataclass(frozen=True)
class Leg:
    km: float
    hours: float
    source: str


@lru_cache
def _table() -> dict[tuple[int, int], Leg]:
    out: dict[tuple[int, int], Leg] = {}
    with open(get_settings().reference_dir / "distances.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            a, b = int(row["from_location_id"]), int(row["to_location_id"])
            leg = Leg(float(row["km"]), float(row["hours"]), row["source"])
            out[(a, b)] = leg
            out.setdefault((b, a), leg)
    return out


def distance(a: int, b: int) -> Leg | None:
    if a == b:
        return _table().get((a, b), Leg(0.0, 0.3, "same location"))
    return _table().get((a, b))
