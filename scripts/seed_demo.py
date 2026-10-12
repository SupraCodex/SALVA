#!/usr/bin/env python3
"""Idempotent demo seed built from the team's reference data.

Reads data/reference/locations.csv and data/reference/markets.csv, then creates:
  - organization "demo"
  - every location (departure point, storage relays)
  - a storage site per "stockage" location (with its capacity)
  - every market (each market gets a location row, as the schema requires)
  - one demo lot: 500 kg of tomatoes, 12 h late, Dschang -> Mboppi (Douala)

Run from the repo root (database reachable, DATABASE_URL set):

    python scripts/seed_demo.py                   # seed
    python scripts/seed_demo.py --create-tables   # also create missing tables

Safe to run many times: every row is looked up by name / marker first.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.models import (
    Base,
    Location,
    Lot,
    Market,
    Organization,
    StorageSite,
)
from app.db.session import SessionLocal, engine

REF = ROOT / "data" / "reference"
DEMO_ORG = "demo"
DEMO_MARKER = "seed_demo"  # stored in Lot.notes to recognise our lot
ORIGIN_NAME = "Zone de production de Dschang"  # type "depart" in locations.csv
DESTINATION_NAME = "Marche Mboppi"  # Douala
PRODUCT = "tomato"


def read_csv(name: str) -> list[dict[str, str]]:
    with (REF / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def get_or_create_org(db) -> Organization:
    org = db.query(Organization).filter_by(name=DEMO_ORG).first()
    if org is None:
        org = Organization(name=DEMO_ORG)
        db.add(org)
        db.flush()
    return org


def get_or_create_location(db, name: str, lat: float, lon: float, source: str) -> Location:
    loc = db.query(Location).filter_by(name=name).first()
    if loc is None:
        loc = Location(name=name, lat=lat, lon=lon, source=source[:200])
        db.add(loc)
        db.flush()
    return loc


def seed_locations_and_storage(db, org) -> dict[str, Location]:
    out: dict[str, Location] = {}
    for row in read_csv("locations.csv"):
        loc = get_or_create_location(
            db, row["nom"], float(row["latitude"]), float(row["longitude"]), row["source"]
        )
        out[row["nom"]] = loc
        if row["type"] == "stockage":
            site = (
                db.query(StorageSite)
                .filter_by(organization_id=org.id, name=row["nom"])
                .first()
            )
            if site is None:
                db.add(
                    StorageSite(
                        organization_id=org.id,
                        location_id=loc.id,
                        name=row["nom"],
                        capacity_kg=float(row["capacite_stockage_kg"]),
                    )
                )
    db.flush()
    return out


def seed_markets(db) -> dict[str, Market]:
    out: dict[str, Market] = {}
    for row in read_csv("markets.csv"):
        loc = get_or_create_location(
            db, row["nom"], float(row["latitude"]), float(row["longitude"]), row["source"]
        )
        m = db.query(Market).filter_by(name=row["nom"]).first()
        if m is None:
            m = Market(
                name=row["nom"],
                location_id=loc.id,
                ref_price_fcfa_kg=float(row["prix_ref_fcfa_kg"]),
                absorb_kg_day=float(row["absorption_kg_jour"]),
                source=row["source"][:200],
            )
            db.add(m)
        out[row["nom"]] = m
    db.flush()
    return out


def seed_demo_lot(db, org, origin, destination) -> bool:
    """500 kg of tomatoes with a 12 h delay. False if already present."""
    if db.query(Lot).filter_by(organization_id=org.id, notes=DEMO_MARKER).first():
        return False
    now = datetime.now(timezone.utc)
    db.add(
        Lot(
            organization_id=org.id,
            product=PRODUCT,
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
        locations = seed_locations_and_storage(db, org)
        markets = seed_markets(db)
        created = seed_demo_lot(
            db, org, locations[ORIGIN_NAME], markets[DESTINATION_NAME]
        )
        db.commit()
        lot = db.query(Lot).filter_by(organization_id=org.id, notes=DEMO_MARKER).first()
        print(
            f"Seed OK: org={DEMO_ORG}, locations={db.query(Location).count()}, "
            f"storage_sites={db.query(StorageSite).count()}, "
            f"markets={db.query(Market).count()}, demo lot id={lot.id} "
            f"({'created' if created else 'already present'})."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
