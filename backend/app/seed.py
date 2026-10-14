"""Idempotent seeds: reference data (locations, markets) and the demonstration workspace.

    python -m app.seed --reference          # locations and markets from data/reference/*.csv
    python -m app.seed --reference --demo   # + demo organization, user, storage site and lot

The demo lot reproduces the demonstration scenario of the design document (§47): 500 kg of
tomatoes harvested on 1 October 06:00, 12 h late, departure in the West, destination Douala,
a storage relay with 200 kg of free capacity, to be analysed in replay mode on 3 October.
The demo password comes from DEMO_USER_PASSWORD, or is generated and printed once.
"""

from __future__ import annotations

import argparse
import csv
import secrets
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Location, Lot, Market, Organization, StorageSite, User
from app.db.session import get_sessionmaker
from app.security import hash_password

DEMO_ORG = "SALVA Demo"
DEMO_NOTE = "Demo lot (design document scenario, section 47)"
KIND = {"depart": "origin", "stockage": "storage"}
DEMO_HARVEST = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)
DEMO_ETA_PLANNED = datetime(2026, 10, 3, 14, 0, tzinfo=UTC)
DEMO_ETA_CURRENT = datetime(2026, 10, 4, 2, 0, tzinfo=UTC)
DEMO_ANALYSIS_AT = datetime(2026, 10, 3, 8, 0, tzinfo=UTC)


def _rows(name: str) -> list[dict[str, str]]:
    path = get_settings().reference_dir / name
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _note(row: dict[str, str]) -> str:
    return f"{row['source'].strip()} ({row['date_source'].strip()})"


def seed_reference(db: Session) -> dict[str, int]:
    counts = {"locations": 0, "markets": 0}
    for row in _rows("locations.csv"):
        code = row["location_id"].strip()
        loc = db.scalar(select(Location).where(Location.code == code))
        values = {
            "label": row["nom"].strip(),
            "kind": KIND.get(row["type"].strip(), "place"),
            "lat": float(row["latitude"]),
            "lon": float(row["longitude"]),
            "source_note": _note(row),
        }
        if loc is None:
            db.add(Location(code=code, **values))
            counts["locations"] += 1
        else:
            for key, value in values.items():
                setattr(loc, key, value)
    db.flush()
    for row in _rows("markets.csv"):
        code = row["market_id"].strip()
        loc = db.scalar(select(Location).where(Location.code == code))
        loc_values = {
            "label": f"{row['nom'].strip()} ({row['ville'].strip()})",
            "kind": "market",
            "lat": float(row["latitude"]),
            "lon": float(row["longitude"]),
            "source_note": _note(row),
        }
        if loc is None:
            loc = Location(code=code, **loc_values)
            db.add(loc)
            db.flush()
        else:
            for key, value in loc_values.items():
                setattr(loc, key, value)
        market = db.scalar(select(Market).where(Market.code == code))
        values = {
            "name": row["nom"].strip(),
            "city": row["ville"].strip(),
            "location_id": loc.id,
            "ref_price_fcfa_kg": float(row["prix_ref_fcfa_kg"]),
            "absorption_kg_day": float(row["absorption_kg_jour"]),
            "assumption_note": _note(row),
        }
        if market is None:
            db.add(Market(code=code, **values))
            counts["markets"] += 1
        else:
            for key, value in values.items():
                setattr(market, key, value)
    db.commit()
    return counts


def seed_demo(db: Session) -> dict[str, str]:
    settings = get_settings()
    out: dict[str, str] = {}
    org = db.scalar(select(Organization).where(Organization.name == DEMO_ORG))
    if org is None:
        org = Organization(name=DEMO_ORG)
        db.add(org)
        db.flush()
    user = db.scalar(select(User).where(User.email == settings.demo_user_email))
    if user is None:
        password = settings.demo_user_password or secrets.token_urlsafe(12)
        user = User(
            organization_id=org.id,
            email=settings.demo_user_email,
            role="admin",
            locale="fr",
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
        out["password"] = password if not settings.demo_user_password else "(from DEMO_USER_PASSWORD)"
    elif settings.demo_user_password:
        user.password_hash = hash_password(settings.demo_user_password)
        user.is_active = True
    out["email"] = user.email
    relay = db.scalar(select(Location).where(Location.code == "L02"))
    origin = db.scalar(select(Location).where(Location.code == "L01"))
    douala = db.scalar(select(Market).where(Market.code == "M01"))
    if relay is None or origin is None or douala is None:
        raise SystemExit("Reference data missing: run `python -m app.seed --reference` first.")
    site = db.scalar(select(StorageSite).where(StorageSite.organization_id == org.id))
    if site is None:
        db.add(
            StorageSite(
                organization_id=org.id,
                location_id=relay.id,
                name="Relais de Bafang (200 kg libres)",
                capacity_kg=200.0,
                temp_mode="ambient_shade",
                cost_fcfa_kg_day=5.0,
            )
        )
    lot = db.scalar(select(Lot).where(Lot.organization_id == org.id, Lot.notes == DEMO_NOTE))
    if lot is None:
        lot = Lot(
            organization_id=org.id,
            created_by=user.id,
            product_code="tomato",
            quantity_kg=500.0,
            harvested_at=DEMO_HARVEST,
            maturity="breaker",
            packaging="crate",
            origin_location_id=origin.id,
            destination_market_id=douala.id,
            eta_planned_at=DEMO_ETA_PLANNED,
            eta_current_at=DEMO_ETA_CURRENT,
            notes=DEMO_NOTE,
        )
        db.add(lot)
    db.commit()
    out["lot_id"] = str(lot.id)
    out["replay_analysis_at"] = DEMO_ANALYSIS_AT.isoformat()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed SALVA reference and demo data (idempotent).")
    parser.add_argument("--reference", action="store_true", help="load locations and markets")
    parser.add_argument("--demo", action="store_true", help="create the demo organization, user and lot")
    args = parser.parse_args(argv)
    if not (args.reference or args.demo):
        parser.error("choose --reference and/or --demo")
    db = get_sessionmaker()()
    try:
        if args.reference:
            print(f"reference: {seed_reference(db)}")
        if args.demo:
            info = seed_demo(db)
            print(f"demo user: {info['email']}")
            if "password" in info:
                print(f"demo password: {info['password']}")
            print(f"demo lot: {info['lot_id']} (replay the analysis at {info['replay_analysis_at']})")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
