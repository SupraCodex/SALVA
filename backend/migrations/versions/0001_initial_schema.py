"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-14 06:25:12.635632

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import app.db.base

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('origin','storage','market','place')",
            name=op.f("ck_locations_kind"),
        ),
        sa.CheckConstraint("lat BETWEEN -90 AND 90", name=op.f("ck_locations_lat")),
        sa.CheckConstraint("lon BETWEEN -180 AND 180", name=op.f("ck_locations_lon")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint("code", name=op.f("uq_locations_code")),
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(name) >= 2", name=op.f("ck_organizations_name_length")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("name", name=op.f("uq_organizations_name")),
    )
    op.create_table(
        "markets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("ref_price_fcfa_kg", sa.Float(), nullable=False),
        sa.Column("absorption_kg_day", sa.Float(), nullable=False),
        sa.Column("assumption_note", sa.Text(), nullable=False),
        sa.CheckConstraint("absorption_kg_day >= 0", name=op.f("ck_markets_absorption")),
        sa.CheckConstraint("ref_price_fcfa_kg > 0", name=op.f("ck_markets_price")),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_markets_location_id_locations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_markets")),
        sa.UniqueConstraint("code", name=op.f("uq_markets_code")),
    )
    op.create_table(
        "storage_sites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("capacity_kg", sa.Float(), nullable=False),
        sa.Column("temp_mode", sa.String(length=20), nullable=False),
        sa.Column("cost_fcfa_kg_day", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "temp_mode IN ('ambient_shade','ventilated','cold_room')",
            name=op.f("ck_storage_sites_temp_mode"),
        ),
        sa.CheckConstraint("capacity_kg > 0", name=op.f("ck_storage_sites_capacity")),
        sa.CheckConstraint("cost_fcfa_kg_day >= 0", name=op.f("ck_storage_sites_cost")),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_storage_sites_location_id_locations"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_storage_sites_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_sites")),
    )
    op.create_index(
        op.f("ix_storage_sites_organization_id"),
        "storage_sites",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("locale", sa.String(length=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("locale IN ('fr','en')", name=op.f("ck_users_locale")),
        sa.CheckConstraint("role IN ('admin','operator')", name=op.f("ck_users_role")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_users_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_organization_id"), "users", ["organization_id"], unique=False)
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("entity", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column(
            "detail",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_logs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        op.f("ix_audit_logs_organization_id"),
        "audit_logs",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "lots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("product_code", sa.String(length=40), nullable=False),
        sa.Column("quantity_kg", sa.Float(), nullable=False),
        sa.Column("harvested_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("maturity", sa.String(length=10), nullable=False),
        sa.Column("packaging", sa.String(length=10), nullable=False),
        sa.Column("origin_location_id", sa.Uuid(), nullable=False),
        sa.Column("destination_market_id", sa.Uuid(), nullable=False),
        sa.Column("eta_planned_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("eta_current_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("temp_override_c", sa.Float(), nullable=True),
        sa.Column("price_override_fcfa_kg", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("maturity IN ('green','breaker','ripe')", name=op.f("ck_lots_maturity")),
        sa.CheckConstraint("packaging IN ('crate','carton','sack')", name=op.f("ck_lots_packaging")),
        sa.CheckConstraint("status IN ('open','decided','closed')", name=op.f("ck_lots_status")),
        sa.CheckConstraint("eta_current_at > harvested_at", name=op.f("ck_lots_eta_after_harvest")),
        sa.CheckConstraint(
            "price_override_fcfa_kg IS NULL OR price_override_fcfa_kg > 0",
            name=op.f("ck_lots_price_override"),
        ),
        sa.CheckConstraint("quantity_kg > 0 AND quantity_kg <= 100000", name=op.f("ck_lots_quantity")),
        sa.CheckConstraint(
            "temp_override_c IS NULL OR (temp_override_c >= 0 AND temp_override_c <= 50)",
            name=op.f("ck_lots_temp_override"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_lots_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["destination_market_id"],
            ["markets.id"],
            name=op.f("fk_lots_destination_market_id_markets"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_lots_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["origin_location_id"],
            ["locations.id"],
            name=op.f("fk_lots_origin_location_id_locations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lots")),
    )
    op.create_index("ix_lots_org_created", "lots", ["organization_id", "created_at"], unique=False)
    op.create_index("ix_lots_org_status", "lots", ["organization_id", "status"], unique=False)
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", app.db.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_refresh_tokens_family_id"),
        "refresh_tokens",
        ["family_id"],
        unique=False,
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=40), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("model_fallback", sa.Boolean(), nullable=False),
        sa.Column("analysis_at", app.db.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("replay", sa.Boolean(), nullable=False),
        sa.Column(
            "features",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "feature_sources",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("loss_p10", sa.Float(), nullable=False),
        sa.Column("loss_p50", sa.Float(), nullable=False),
        sa.Column("loss_p90", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.Column(
            "risk_detail",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "top_factors",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("shelf_life_p50_h", sa.Float(), nullable=True),
        sa.Column(
            "extrapolated",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("risk_level IN ('low','medium','high')", name=op.f("ck_analyses_risk_level")),
        sa.CheckConstraint(
            "loss_p10 >= 0 AND loss_p90 <= 1 AND loss_p10 <= loss_p50 AND loss_p50 <= loss_p90",
            name=op.f("ck_analyses_loss_quantiles"),
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name=op.f("fk_analyses_lot_id_lots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
    )
    op.create_index("ix_analyses_lot_created", "analyses", ["lot_id", "created_at"], unique=False)
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("n_draws", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("risk_profile", sa.String(length=10), nullable=False),
        sa.Column(
            "assumptions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "request",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_profile IN ('prudent','balanced','ambitious')",
            name=op.f("ck_simulation_runs_risk_profile"),
        ),
        sa.CheckConstraint("n_draws BETWEEN 100 AND 20000", name=op.f("ck_simulation_runs_n_draws")),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_simulation_runs_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simulation_runs")),
    )
    op.create_index(
        op.f("ix_simulation_runs_analysis_id"),
        "simulation_runs",
        ["analysis_id"],
        unique=False,
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("simulation_run_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=True),
        sa.Column("storage_site_id", sa.Uuid(), nullable=True),
        sa.Column(
            "label",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "allocation",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("feasible", sa.Boolean(), nullable=False),
        sa.Column("infeasible_reason", sa.String(length=60), nullable=True),
        sa.Column("discouraged", sa.Boolean(), nullable=False),
        sa.Column("discouraged_reason", sa.String(length=60), nullable=True),
        sa.Column(
            "results",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("prob_best", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "action IN ('continue','store','reroute','sell_local','optimized_split')",
            name=op.f("ck_scenarios_action"),
        ),
        sa.CheckConstraint("prob_best >= 0 AND prob_best <= 1", name=op.f("ck_scenarios_prob_best")),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], name=op.f("fk_scenarios_market_id_markets")),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_scenarios_simulation_run_id_simulation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["storage_site_id"],
            ["storage_sites.id"],
            name=op.f("fk_scenarios_storage_site_id_storage_sites"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenarios")),
    )
    op.create_index(
        op.f("ix_scenarios_simulation_run_id"),
        "scenarios",
        ["simulation_run_id"],
        unique=False,
    )
    op.create_table(
        "outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid(), nullable=False),
        sa.Column("simulation_run_id", sa.Uuid(), nullable=True),
        sa.Column("scenario_id", sa.Uuid(), nullable=True),
        sa.Column("decision_taken", sa.String(length=20), nullable=False),
        sa.Column("followed_reco", sa.Boolean(), nullable=True),
        sa.Column("actual_recovered_kg", sa.Float(), nullable=True),
        sa.Column("actual_revenue_fcfa", sa.Float(), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column(
            "recorded_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision_taken IN ('continue','store','reroute','sell_local','optimized_split','other')",
            name=op.f("ck_outcomes_decision"),
        ),
        sa.CheckConstraint(
            "actual_recovered_kg IS NULL OR actual_recovered_kg >= 0",
            name=op.f("ck_outcomes_kg"),
        ),
        sa.CheckConstraint(
            "actual_revenue_fcfa IS NULL OR actual_revenue_fcfa >= 0",
            name=op.f("ck_outcomes_revenue"),
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name=op.f("fk_outcomes_lot_id_lots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["users.id"],
            name=op.f("fk_outcomes_recorded_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.id"],
            name=op.f("fk_outcomes_scenario_id_scenarios"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_outcomes_simulation_run_id_simulation_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outcomes")),
    )
    op.create_index(op.f("ix_outcomes_lot_id"), "outcomes", ["lot_id"], unique=False)
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("simulation_run_id", sa.Uuid(), nullable=False),
        sa.Column("best_scenario_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.String(length=10), nullable=False),
        sa.Column("no_clear_winner", sa.Boolean(), nullable=False),
        sa.Column(
            "rationale_codes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "ranked_keys",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "scores_fcfa",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("prob_best", sa.Float(), nullable=False),
        sa.Column("gap_fraction", sa.Float(), nullable=True),
        sa.Column(
            "policy",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "assumption_codes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IN ('high','medium','low','none')",
            name=op.f("ck_recommendations_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["best_scenario_id"],
            ["scenarios.id"],
            name=op.f("fk_recommendations_best_scenario_id_scenarios"),
        ),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_recommendations_simulation_run_id_simulation_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendations")),
        sa.UniqueConstraint("simulation_run_id", name=op.f("uq_recommendations_simulation_run_id")),
    )
    op.create_table(
        "explanations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.String(length=200), nullable=True),
        sa.Column(
            "content",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("lang IN ('fr','en')", name=op.f("ck_explanations_lang")),
        sa.CheckConstraint("source IN ('template','llm')", name=op.f("ck_explanations_source")),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            name=op.f("fk_explanations_recommendation_id_recommendations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_explanations")),
    )
    op.create_index(
        op.f("ix_explanations_recommendation_id"),
        "explanations",
        ["recommendation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_explanations_recommendation_id"), table_name="explanations")
    op.drop_table("explanations")
    op.drop_table("recommendations")
    op.drop_index(op.f("ix_outcomes_lot_id"), table_name="outcomes")
    op.drop_table("outcomes")
    op.drop_index(op.f("ix_scenarios_simulation_run_id"), table_name="scenarios")
    op.drop_table("scenarios")
    op.drop_index(op.f("ix_simulation_runs_analysis_id"), table_name="simulation_runs")
    op.drop_table("simulation_runs")
    op.drop_index("ix_analyses_lot_created", table_name="analyses")
    op.drop_table("analyses")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_lots_org_status", table_name="lots")
    op.drop_index("ix_lots_org_created", table_name="lots")
    op.drop_table("lots")
    op.drop_index(op.f("ix_audit_logs_organization_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_storage_sites_organization_id"), table_name="storage_sites")
    op.drop_table("storage_sites")
    op.drop_table("markets")
    op.drop_table("organizations")
    op.drop_table("locations")
