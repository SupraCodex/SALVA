from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Location, Market, StorageSite


def locations(db: Session) -> list[Location]:
    return list(db.scalars(select(Location).order_by(Location.name)))


def location(db: Session, location_id: int) -> Location | None:
    return db.get(Location, location_id)


def markets(db: Session) -> list[Market]:
    return list(db.scalars(select(Market).order_by(Market.name)))


def market(db: Session, market_id: int) -> Market | None:
    return db.get(Market, market_id)


def storage_sites(db: Session, org_id: int) -> list[StorageSite]:
    return list(db.scalars(select(StorageSite).where(StorageSite.organization_id == org_id)
                           .order_by(StorageSite.name)))


def save(db: Session, obj):
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
