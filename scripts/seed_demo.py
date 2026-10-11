#!/usr/bin/env python3
"""Idempotent demo seed: org "demo", reference places/markets, one demo lot.

Run from the repo root (PostgreSQL up, DATABASE_URL set, tables created):

    python scripts/seed_demo.py                # seed
    python scripts/seed_demo.py --create-tables   # also create missing tables

Safe to run many times: every row is looked up by name / marker first.
Reference numbers below are DEMO PLACEHOLDERS (source="demo assumption"):
replace them with the team's real reference values if they differ.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.models import Base, Location, Lot, Market, Organization  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402

DEMO_ORG = "demo"
DEMO_MARKER = "seed_demo"  # stored in Lot.notes to recognise our lot

# name, lat, lon
LOCATIONS = [
    ("Bafoussam", 5.4737, 10.4179),
    ("Douala", 4.0511, 9.7679),
    ("Yaoundé", 3.8480, 11.5021),
]
# name, location name, ref price FCFA/kg, absorb kg/day  (placeholders)
MARKETS = [
    ("Marché de Douala", "Douala", 400.0, 5000.0),
    ("Marché de Yaoundé", "Yaoundé", 450.0, 4000.0),
]
ORIGIN = "Bafoussam"
DESTINATION = "Marché de Douala"


def get_or_create_org(db) -> Organization:
    org = db.query(Organization).filter_by(name=DEMO_ORG).first()
    if org is None:
        org = Organization(name=DEMO_ORG)
        db.add(org)
        db.flush()
    return org


def seed_locations(db) -> dict[str, Location]:
    out = {}
    for name, lat, lon in LOCATIONS:
        loc = db.query(Location).filter_by(name=name).first()
        if loc is None:
            loc = Location(name=name, lat=lat, lon=lon, source="demo assumption")
            db.add(loc)
        out[name] = loc
    db.flush()
    return out


def seed_markets(db, locations: dict[str, Location]) -> dict[str, Market]:
    out = {}
    for name, loc_name, price, absorb in MARKETS:
        m = db.query(Market).filter_by(name=name).first()
        if m is None:
            m = Market(
                name=name,
                location_id=locations[loc_name].id,
                ref_price_fcfa_kg=price,
                absorb_kg_day=absorb,
                source="demo assumption",
            )
            db.add(m)
        out[name] = m
    db.flush()
    return out


def seed_demo_lot(db, org, origin, destination) -> bool:
    """500 kg of tomatoes with a 12 h delay. False if already present."""
    exists = (
        db.query(Lot)
        .filter_by(organization_id=org.id, notes=DEMO_MARKER)
        .first()
    )
    if exists:
        return False
    now = datetime.now(timezone.utc)
    db.add(
        Lot(
            organization_id=org.id,
            product="tomato",
            kg=500,
            harvested_at=now - timedelta(hours=20),
            maturity="breaker",
            packaging="crate",
            origin_id=origin.id,
            destination_id=destination.id,
            eta_planned=now + timedelta(hours=2),
            eta_current=now + timedelta(hours=14),  # planned + 12 h of delay
            temp_override_c=None,
            notes=DEMO_MARKER,
            status="open",
        )
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-tables", action="store_true",
                        help="create missing tables first (no migration tool needed)")
    args = parser.parse_args()
    if args.create_tables:
        Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        org = get_or_create_org(db)
        locations = seed_locations(db)
        markets = seed_markets(db, locations)
        created = seed_demo_lot(db, org, locations[ORIGIN], markets[DESTINATION])
        db.commit()
        lot = db.query(Lot).filter_by(organization_id=org.id, notes=DEMO_MARKER).first()
        print(f"Seed OK: org={DEMO_ORG}, locations={len(locations)}, "
              f"markets={len(markets)}, demo lot id={lot.id} "
              f"({'created' if created else 'already present'}).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
