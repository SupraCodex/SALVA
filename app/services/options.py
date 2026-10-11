"""options_for: which actions really exist for this lot. An impossible action is never simulated.

- continue    always
- store       only if the organization has a storage site (partial if capacity < lot: RM-2)
- reroute     only to markets whose distance from the origin is known (distances.csv)
- sell_local  nearest market to the origin within SELL_LOCAL_RADIUS_KM

Assumption (returned to the client): reroute and storage are computed from the origin,
because the truck's live position is unknown.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Lot
from app.integrations.fallback_distances import distance
from app.repositories import reference as ref_repo


def _market(m, price: float | None = None, absorb: dict[int, float] | None = None):
    from salva_core.contracts import Market
    return Market(m.id, m.name, float(price or m.ref_price_fcfa_kg),
                  float((absorb or {}).get(m.id, m.absorb_kg_day)))


def options_for(db: Session, clot, lot: Lot, p, dest_price: float,
                absorb: dict[int, float]) -> tuple[list, list[dict]]:
    """clot: salva_core Lot; p: salva_core ProductParams. Returns (salva_core Scenarios, assumptions)."""
    from salva_core.contracts import Option, Scenario
    s = get_settings()
    assumptions: list[dict] = []
    origin = lot.origin_id
    dest = _market(lot.destination, dest_price, absorb)
    d_dest = distance(origin, lot.destination.location_id)
    cont = Option(f"continue:{dest.id}", "continue", clot.kg, dest)
    scenarios = [Scenario("continue", "continue", (cont,))]

    # ---- sell_local: nearest market to the origin (excluding the planned destination)
    local_m, local_d = None, None
    for m in ref_repo.markets(db):
        if m.id == dest.id:
            continue
        d = distance(origin, m.location_id)
        if d and d.km <= s.sell_local_radius_km and (local_d is None or d.km < local_d.km):
            local_m, local_d = m, d
    if local_m is not None and (d_dest is None or local_d.km < d_dest.km):
        opt = Option(f"sell_local:{local_m.id}", "sell_local", clot.kg, _market(local_m, absorb=absorb),
                     extra_h=local_d.hours - clot.remaining_h)
        scenarios.append(Scenario(opt.id, "sell_local", (opt,)))
    else:
        local_m = None
        scenarios.append(Scenario("sell_local", "sell_local", (), False, "NO_LOCAL_MARKET"))

    # ---- reroute: other markets with a known distance (the local market is already its own action)
    rer = []
    for m in ref_repo.markets(db):
        if m.id in (dest.id, getattr(local_m, "id", None)):
            continue
        d = distance(origin, m.location_id)
        if d is not None:
            rer.append((d, m))
    rer.sort(key=lambda t: t[0].km)
    if not rer or d_dest is None:
        scenarios.append(Scenario("reroute", "reroute", (), False,
                                  "NO_KNOWN_DISTANCE" if d_dest is None else "NO_ALTERNATIVE_MARKET"))
    for d, m in rer[: s.max_reroute_options]:
        opt = Option(f"reroute:{m.id}", "reroute", clot.kg, _market(m, absorb=absorb),
                     extra_h=d.hours - d_dest.hours,
                     cost_per_kg=s.transport_fcfa_kg_km * max(0.0, d.km - d_dest.km),
                     detail={"km": d.km, "distance_source": d.source})
        scenarios.append(Scenario(opt.id, "reroute", (opt,)))

    # ---- store: up to 2 sites, nearest to the origin; the stored share is sold one day later
    sites = ref_repo.storage_sites(db, lot.organization_id)
    sites.sort(key=lambda st: (distance(origin, st.location_id) or _FAR).km)
    if not sites:
        scenarios.append(Scenario("store", "store", (), False, "NO_STORAGE_SITE"))
    for st in sites[:2]:
        a = distance(origin, st.location_id)
        b = distance(st.location_id, lot.destination.location_id)
        detour_km = max(0.0, a.km + b.km - d_dest.km) if a and b and d_dest else 0.0
        detour_h = max(0.0, a.hours + b.hours - d_dest.hours) if a and b and d_dest else 0.0
        if not (a and b and d_dest):
            assumptions.append({"name": f"detour:{st.name}", "value": 0, "source": "assumption (distance unknown)"})
        hold = s.hold_h
        # one temperature for the whole exposure: the storage offset is weighted by its share of the time
        offset = p.storage_temp_offset_c.get(st.temp_mode, 0.0) * hold / max(clot.remaining_h + hold, 1e-6)
        stored = min(clot.kg, st.capacity_kg)
        leg = Option(f"store:{st.id}", "store", stored, dest, extra_h=hold + detour_h, temp_offset=offset,
                     cost_per_kg=st.cost_fcfa_kg_day * hold / 24.0 + s.transport_fcfa_kg_km * detour_km,
                     is_store=True, site_id=st.id, site_name=st.name, store_capacity_kg=st.capacity_kg)
        legs = (leg,) + ((cont.with_kg(clot.kg - stored),) if clot.kg - stored > 0 else ())
        scenarios.append(Scenario(leg.id, "store", legs))

    assumptions += [
        {"name": "hold_h", "value": s.hold_h, "source": "default"},
        {"name": "transport_fcfa_kg_km", "value": s.transport_fcfa_kg_km, "source": "default"},
        {"name": "position", "value": "origin", "source": "assumption (live truck position unknown)"},
    ]
    if d_dest:
        assumptions.append({"name": "distance_km:origin->destination", "value": d_dest.km, "source": d_dest.source})
    return scenarios, assumptions


class _Far:
    km = float("inf")


_FAR = _Far()
