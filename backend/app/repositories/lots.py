from __future__ import annotations

import base64
import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import Analysis, Lot, Outcome, Recommendation, SimulationRun


def get(db: Session, org_id: uuid.UUID, lot_id: uuid.UUID) -> Lot | None:
    return db.scalar(select(Lot).where(Lot.id == lot_id, Lot.organization_id == org_id))


def encode_cursor(lot: Lot) -> str:
    raw = f"{lot.created_at.isoformat()}|{lot.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    stamp, ident = raw.split("|", 1)
    return datetime.fromisoformat(stamp), uuid.UUID(ident)


def list_(
    db: Session, org_id: uuid.UUID, limit: int, cursor: str | None, status: str | None
) -> tuple[list[Lot], str | None]:
    stmt = select(Lot).where(Lot.organization_id == org_id)
    if status:
        stmt = stmt.where(Lot.status == status)
    if cursor:
        stamp, ident = decode_cursor(cursor)
        stmt = stmt.where(or_(Lot.created_at < stamp, and_(Lot.created_at == stamp, Lot.id < ident)))
    rows = list(db.scalars(stmt.order_by(Lot.created_at.desc(), Lot.id.desc()).limit(limit + 1)))
    next_cursor = encode_cursor(rows[limit - 1]) if len(rows) > limit else None
    return rows[:limit], next_cursor


def latest_analysis(db: Session, lot_id: uuid.UUID) -> Analysis | None:
    return db.scalar(
        select(Analysis).where(Analysis.lot_id == lot_id).order_by(Analysis.created_at.desc()).limit(1)
    )


def analyses(db: Session, lot_id: uuid.UUID) -> list[Analysis]:
    return list(
        db.scalars(select(Analysis).where(Analysis.lot_id == lot_id).order_by(Analysis.created_at.desc()))
    )


def simulations_for(db: Session, analysis_id: uuid.UUID) -> list[SimulationRun]:
    return list(
        db.scalars(
            select(SimulationRun)
            .where(SimulationRun.analysis_id == analysis_id)
            .order_by(SimulationRun.created_at.desc())
        )
    )


def latest_simulation(db: Session, analysis_id: uuid.UUID) -> SimulationRun | None:
    return db.scalar(
        select(SimulationRun)
        .where(SimulationRun.analysis_id == analysis_id)
        .order_by(SimulationRun.created_at.desc())
        .limit(1)
    )


def outcomes(db: Session, lot_id: uuid.UUID) -> list[Outcome]:
    return list(
        db.scalars(select(Outcome).where(Outcome.lot_id == lot_id).order_by(Outcome.recorded_at.desc()))
    )


def analysis(db: Session, org_id: uuid.UUID, analysis_id: uuid.UUID) -> Analysis | None:
    return db.scalar(
        select(Analysis).join(Lot).where(Analysis.id == analysis_id, Lot.organization_id == org_id)
    )


def simulation(db: Session, org_id: uuid.UUID, simulation_id: uuid.UUID) -> SimulationRun | None:
    return db.scalar(
        select(SimulationRun)
        .join(Analysis, SimulationRun.analysis_id == Analysis.id)
        .join(Lot, Analysis.lot_id == Lot.id)
        .where(SimulationRun.id == simulation_id, Lot.organization_id == org_id)
    )


def recommendation(db: Session, org_id: uuid.UUID, reco_id: uuid.UUID) -> Recommendation | None:
    return db.scalar(
        select(Recommendation)
        .join(SimulationRun, Recommendation.simulation_run_id == SimulationRun.id)
        .join(Analysis, SimulationRun.analysis_id == Analysis.id)
        .join(Lot, Analysis.lot_id == Lot.id)
        .where(Recommendation.id == reco_id, Lot.organization_id == org_id)
    )
