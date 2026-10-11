from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False, default="assumption")
    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="ck_loc_lat"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="ck_loc_lon"),
    )


class Market(Base):
    __tablename__ = "markets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    ref_price_fcfa_kg: Mapped[float] = mapped_column(Float, nullable=False)
    absorb_kg_day: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False, default="assumption")
    location: Mapped[Location] = relationship(lazy="joined")
    __table_args__ = (
        CheckConstraint("ref_price_fcfa_kg > 0", name="ck_market_price"),
        CheckConstraint("absorb_kg_day >= 0", name="ck_market_absorb"),
    )


class StorageSite(Base):
    __tablename__ = "storage_sites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    capacity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    temp_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    cost_fcfa_kg_day: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    location: Mapped[Location] = relationship(lazy="joined")
    __table_args__ = (
        CheckConstraint("capacity_kg > 0", name="ck_site_capacity"),
        CheckConstraint("temp_mode IN ('ambient_shade','ventilated','cold_room')", name="ck_site_mode"),
        CheckConstraint("cost_fcfa_kg_day >= 0", name="ck_site_cost"),
    )
