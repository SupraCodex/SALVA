"""Lots and outcomes. EVERY query is filtered by organization."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Lot, Outcome


def get(db: Session, org_id: int, lot_id: int) -> Lot | None:
    return db.scalar(select(Lot).where(Lot.id == lot_id, Lot.organization_id == org_id))


def list_(db: Session, org_id: int, limit: int, offset: int, status: str | None) -> tuple[list[Lot], int]:
    q = select(Lot).where(Lot.organization_id == org_id)
    if status:
        q = q.where(Lot.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Lot.created_at.desc(), Lot.id.desc()).limit(limit).offset(offset))
    return list(rows), int(total or 0)


def save(db: Session, lot: Lot) -> Lot:
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


def outcomes(db: Session, lot_id: int) -> list[Outcome]:
    return list(db.scalars(select(Outcome).where(Outcome.lot_id == lot_id).order_by(Outcome.recorded_at.desc())))
