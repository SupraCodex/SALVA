from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Location, Market, MarketSetting, StorageSite


def locations(db: Session) -> list[Location]:
    return list(db.scalars(select(Location).order_by(Location.kind, Location.label)))


def location(db: Session, location_id: uuid.UUID) -> Location | None:
    return db.get(Location, location_id)


def markets(db: Session) -> list[Market]:
    return list(db.scalars(select(Market).order_by(Market.city, Market.name)))


def market(db: Session, market_id: uuid.UUID) -> Market | None:
    return db.get(Market, market_id)


def market_settings(db: Session, org_id: uuid.UUID) -> dict[uuid.UUID, MarketSetting]:
    rows = db.scalars(select(MarketSetting).where(MarketSetting.organization_id == org_id))
    return {row.market_id: row for row in rows}


def market_setting(db: Session, org_id: uuid.UUID, market_id: uuid.UUID) -> MarketSetting | None:
    return db.scalar(
        select(MarketSetting).where(
            MarketSetting.organization_id == org_id, MarketSetting.market_id == market_id
        )
    )


def storage_sites(db: Session, org_id: uuid.UUID, active_only: bool = False) -> list[StorageSite]:
    stmt = select(StorageSite).where(StorageSite.organization_id == org_id)
    if active_only:
        stmt = stmt.where(StorageSite.is_active.is_(True))
    return list(db.scalars(stmt.order_by(StorageSite.name)))


def storage_site(db: Session, org_id: uuid.UUID, site_id: uuid.UUID) -> StorageSite | None:
    return db.scalar(
        select(StorageSite).where(StorageSite.id == site_id, StorageSite.organization_id == org_id)
    )
