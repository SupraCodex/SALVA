"""Analysis results are immutable: never updated, a new analysis is created instead."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JSONType, UTCDateTime, created_at
from .lot import Lot


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"), index=True)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    model_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    analyzed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    n_draws: Mapped[int] = mapped_column(Integer, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONType, nullable=False)
    assumptions: Mapped[list] = mapped_column(JSONType, nullable=False)
    loss_p10: Mapped[float] = mapped_column(Float, nullable=False)
    loss_p50: Mapped[float] = mapped_column(Float, nullable=False)
    loss_p90: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    factors: Mapped[list] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = created_at()

    lot: Mapped[Lot] = relationship(lazy="joined")
    scenarios: Mapped[list["ScenarioRow"]] = relationship(lazy="selectin", order_by="ScenarioRow.position")
    recommendation: Mapped["Recommendation | None"] = relationship(lazy="selectin", uselist=False)

    __table_args__ = (
        CheckConstraint("loss_p10 >= 0 AND loss_p90 <= 1 AND loss_p10 <= loss_p50 AND loss_p50 <= loss_p90",
                        name="ck_analysis_loss"),
        CheckConstraint("risk_level IN ('low','medium','high')", name="ck_analysis_risk"),
        CheckConstraint("n_draws BETWEEN 100 AND 20000", name="ck_analysis_draws"),
    )


class ScenarioRow(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    allocation: Mapped[list] = mapped_column(JSONType, nullable=False)
    feasible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    infeasible_reason: Mapped[str | None] = mapped_column(String(60))
    kg_equiv: Mapped[dict | None] = mapped_column(JSONType)
    net_value_fcfa: Mapped[dict | None] = mapped_column(JSONType)
    prob_best: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    __table_args__ = (
        CheckConstraint("action IN ('continue','store','reroute','sell_local','optimized_split')",
                        name="ck_scenario_action"),
        CheckConstraint("prob_best BETWEEN 0 AND 1", name="ck_scenario_prob"),
    )


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), unique=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id"))  # NULL = no clear winner
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    rationale: Mapped[list] = mapped_column(JSONType, nullable=False)
    tied: Mapped[list] = mapped_column(JSONType, nullable=False)
    policy: Mapped[dict] = mapped_column(JSONType, nullable=False)
    __table_args__ = (
        CheckConstraint("confidence IN ('high','medium','low','none')", name="ck_reco_confidence"),
    )


class Explanation(Base):
    __tablename__ = "explanations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    lang: Mapped[str] = mapped_column(String(2), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(20))
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    content: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        CheckConstraint("lang IN ('fr','en')", name="ck_expl_lang"),
        CheckConstraint("source IN ('template','llm')", name="ck_expl_source"),
    )
