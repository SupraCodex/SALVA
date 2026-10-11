from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UTCDateTime, created_at
from .reference import Location, Market


class Lot(Base):
    __tablename__ = "lots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    product: Mapped[str] = mapped_column(String(40), nullable=False)
    kg: Mapped[float] = mapped_column(Float, nullable=False)
    harvested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    maturity: Mapped[str] = mapped_column(String(10), nullable=False)
    packaging: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    destination_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False)
    eta_planned: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    eta_current: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    temp_override_c: Mapped[float | None] = mapped_column(Float)
    price_override_fcfa_kg: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(String(500))  # NEVER sent to the LLM
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    created_at: Mapped[datetime] = created_at()

    origin: Mapped[Location] = relationship(lazy="joined")
    destination: Mapped[Market] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("kg > 0 AND kg <= 100000", name="ck_lot_kg"),
        CheckConstraint("maturity IN ('green','breaker','ripe')", name="ck_lot_maturity"),
        CheckConstraint("packaging IN ('crate','carton','sack')", name="ck_lot_packaging"),
        CheckConstraint("status IN ('open','decided','closed')", name="ck_lot_status"),
        Index("ix_lots_org_created", "organization_id", "created_at"),
    )


class Outcome(Base):  # wave 2: decision taken and real result
    __tablename__ = "outcomes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analyses.id", ondelete="SET NULL"))
    decision_taken: Mapped[str] = mapped_column(String(30), nullable=False)
    followed_reco: Mapped[bool | None] = mapped_column(Boolean)
    actual_kg: Mapped[float | None] = mapped_column(Float)
    actual_revenue_fcfa: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint("actual_kg >= 0", name="ck_outcome_kg"),
        CheckConstraint("actual_revenue_fcfa >= 0", name="ck_outcome_rev"),
    )
