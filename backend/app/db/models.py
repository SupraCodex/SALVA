"""SQLAlchemy models (design document §25).

Analyses, simulation runs, scenarios and recommendations are immutable once written: a new
row is created instead of an UPDATE, which keeps the prediction -> decision -> outcome loop
traceable. Every business row is scoped to an organization, directly or through its lot.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JSONType, UTCDateTime, created_at, uuid_pk


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (CheckConstraint("length(name) >= 2", name="name_length"),)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="operator")
    locale: Mapped[str] = mapped_column(String(2), nullable=False, default="fr")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at()
    organization: Mapped[Organization] = relationship(lazy="joined")
    __table_args__ = (
        CheckConstraint("role IN ('admin','operator')", name="role"),
        CheckConstraint("locale IN ('fr','en')", name="locale"),
    )


class RefreshToken(Base):
    """Opaque refresh token, stored hashed, rotated on every use (SEC-02)."""

    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = created_at()


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="place")
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    source_note: Mapped[str] = mapped_column(Text, nullable=False, default="assumption")
    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="lon"),
        CheckConstraint("kind IN ('origin','storage','market','place')", name="kind"),
    )


class Market(Base):
    __tablename__ = "markets"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), nullable=False)
    ref_price_fcfa_kg: Mapped[float] = mapped_column(Float, nullable=False)
    absorption_kg_day: Mapped[float] = mapped_column(Float, nullable=False)
    assumption_note: Mapped[str] = mapped_column(Text, nullable=False, default="assumption")
    location: Mapped[Location] = relationship(lazy="joined")
    __table_args__ = (
        CheckConstraint("ref_price_fcfa_kg > 0", name="price"),
        CheckConstraint("absorption_kg_day >= 0", name="absorption"),
    )


class MarketSetting(Base):
    """An organization's own price and absorption for a reference market (FR-20)."""

    __tablename__ = "market_settings"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), nullable=False)
    price_fcfa_kg: Mapped[float | None] = mapped_column(Float)
    absorption_kg_day: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = created_at()
    __table_args__ = (
        Index("uq_market_settings_org_market", "organization_id", "market_id", unique=True),
        CheckConstraint("price_fcfa_kg IS NULL OR price_fcfa_kg > 0", name="price"),
        CheckConstraint("absorption_kg_day IS NULL OR absorption_kg_day >= 0", name="absorption"),
    )


class StorageSite(Base):
    __tablename__ = "storage_sites"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    capacity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    temp_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    cost_fcfa_kg_day: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at()
    location: Mapped[Location] = relationship(lazy="joined")
    __table_args__ = (
        CheckConstraint("capacity_kg > 0", name="capacity"),
        CheckConstraint("temp_mode IN ('ambient_shade','ventilated','cold_room')", name="temp_mode"),
        CheckConstraint("cost_fcfa_kg_day >= 0", name="cost"),
    )


class Lot(Base):
    __tablename__ = "lots"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    product_code: Mapped[str] = mapped_column(String(40), nullable=False)
    quantity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    harvested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    maturity: Mapped[str] = mapped_column(String(10), nullable=False)
    packaging: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), nullable=False)
    destination_market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    eta_planned_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    eta_current_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    temp_override_c: Mapped[float | None] = mapped_column(Float)
    price_override_fcfa_kg: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(String(500))  # never sent to the LLM
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    created_at: Mapped[datetime] = created_at()

    origin: Mapped[Location] = relationship(lazy="joined")
    destination: Mapped[Market] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("quantity_kg > 0 AND quantity_kg <= 100000", name="quantity"),
        CheckConstraint("maturity IN ('green','breaker','ripe')", name="maturity"),
        CheckConstraint("packaging IN ('crate','carton','sack')", name="packaging"),
        CheckConstraint("status IN ('open','decided','closed')", name="status"),
        CheckConstraint("eta_current_at > harvested_at", name="eta_after_harvest"),
        CheckConstraint(
            "temp_override_c IS NULL OR (temp_override_c >= 0 AND temp_override_c <= 50)",
            name="temp_override",
        ),
        CheckConstraint(
            "price_override_fcfa_kg IS NULL OR price_override_fcfa_kg > 0",
            name="price_override",
        ),
        Index("ix_lots_org_created", "organization_id", "created_at"),
        Index("ix_lots_org_status", "organization_id", "status"),
    )


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[uuid.UUID] = uuid_pk()
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(40), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    analysis_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    replay: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    features: Mapped[dict] = mapped_column(JSONType, nullable=False)
    feature_sources: Mapped[dict] = mapped_column(JSONType, nullable=False)
    loss_p10: Mapped[float] = mapped_column(Float, nullable=False)
    loss_p50: Mapped[float] = mapped_column(Float, nullable=False)
    loss_p90: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    risk_detail: Mapped[dict] = mapped_column(JSONType, nullable=False)
    top_factors: Mapped[list] = mapped_column(JSONType, nullable=False)
    shelf_life_p50_h: Mapped[float | None] = mapped_column(Float)
    extrapolated: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = created_at()

    lot: Mapped[Lot] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "loss_p10 >= 0 AND loss_p90 <= 1 AND loss_p10 <= loss_p50 AND loss_p50 <= loss_p90",
            name="loss_quantiles",
        ),
        CheckConstraint("risk_level IN ('low','medium','high')", name="risk_level"),
        Index("ix_analyses_lot_created", "lot_id", "created_at"),
    )


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    n_draws: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(10), nullable=False)
    assumptions: Mapped[list] = mapped_column(JSONType, nullable=False)
    request: Mapped[dict] = mapped_column(JSONType, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = created_at()

    analysis: Mapped[Analysis] = relationship(lazy="joined")
    scenarios: Mapped[list[Scenario]] = relationship(lazy="selectin", order_by="Scenario.position")
    recommendation: Mapped[Recommendation | None] = relationship(
        lazy="selectin", uselist=False, back_populates="simulation_run"
    )

    __table_args__ = (
        CheckConstraint("n_draws BETWEEN 100 AND 20000", name="n_draws"),
        CheckConstraint("risk_profile IN ('prudent','balanced','ambitious')", name="risk_profile"),
    )


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[uuid.UUID] = uuid_pk()
    simulation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    market_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("markets.id"))
    storage_site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("storage_sites.id", ondelete="SET NULL")
    )
    label: Mapped[dict] = mapped_column(JSONType, nullable=False)
    allocation: Mapped[list] = mapped_column(JSONType, nullable=False)
    feasible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    infeasible_reason: Mapped[str | None] = mapped_column(String(60))
    discouraged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discouraged_reason: Mapped[str | None] = mapped_column(String(60))
    results: Mapped[dict] = mapped_column(JSONType, nullable=False)
    prob_best: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    __table_args__ = (
        CheckConstraint(
            "action IN ('continue','store','reroute','sell_local','optimized_split')",
            name="action",
        ),
        CheckConstraint("prob_best >= 0 AND prob_best <= 1", name="prob_best"),
    )


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[uuid.UUID] = uuid_pk()
    simulation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    best_scenario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenarios.id"))
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    no_clear_winner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rationale_codes: Mapped[list] = mapped_column(JSONType, nullable=False)
    ranked_keys: Mapped[list] = mapped_column(JSONType, nullable=False)
    scores_fcfa: Mapped[dict] = mapped_column(JSONType, nullable=False)
    prob_best: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gap_fraction: Mapped[float | None] = mapped_column(Float)
    policy: Mapped[dict] = mapped_column(JSONType, nullable=False)
    assumption_codes: Mapped[list] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = created_at()

    simulation_run: Mapped[SimulationRun] = relationship(lazy="joined", back_populates="recommendation")
    __table_args__ = (CheckConstraint("confidence IN ('high','medium','low','none')", name="confidence"),)


class Explanation(Base):
    __tablename__ = "explanations"
    id: Mapped[uuid.UUID] = uuid_pk()
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lang: Mapped[str] = mapped_column(String(2), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40))
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint("lang IN ('fr','en')", name="lang"),
        CheckConstraint("source IN ('template','llm')", name="source"),
    )


class Outcome(Base):
    """Decision actually taken and, later, the real result (FR-15). Kept apart from training data."""

    __tablename__ = "outcomes"
    id: Mapped[uuid.UUID] = uuid_pk()
    lot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    simulation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="SET NULL")
    )
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenarios.id", ondelete="SET NULL"))
    decision_taken: Mapped[str] = mapped_column(String(20), nullable=False)
    followed_reco: Mapped[bool | None] = mapped_column(Boolean)
    actual_recovered_kg: Mapped[float | None] = mapped_column(Float)
    actual_revenue_fcfa: Mapped[float | None] = mapped_column(Float)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recorded_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint(
            "decision_taken IN ('continue','store','reroute','sell_local','optimized_split','other')",
            name="decision",
        ),
        CheckConstraint("actual_recovered_kg IS NULL OR actual_recovered_kg >= 0", name="kg"),
        CheckConstraint("actual_revenue_fcfa IS NULL OR actual_revenue_fcfa >= 0", name="revenue"),
    )


class AuditLog(Base):
    """Sensitive actions (SEC-08). Holds identifiers only, never secrets or free text."""

    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    at: Mapped[datetime] = created_at()
