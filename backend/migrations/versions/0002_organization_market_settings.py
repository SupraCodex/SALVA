"""organization market settings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14 11:41:52.501825

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.base

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("price_fcfa_kg", sa.Float(), nullable=True),
        sa.Column("absorption_kg_day", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            app.db.base.UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "absorption_kg_day IS NULL OR absorption_kg_day >= 0",
            name=op.f("ck_market_settings_absorption"),
        ),
        sa.CheckConstraint(
            "price_fcfa_kg IS NULL OR price_fcfa_kg > 0", name=op.f("ck_market_settings_price")
        ),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["markets.id"],
            name=op.f("fk_market_settings_market_id_markets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_market_settings_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_settings")),
    )
    op.create_index(
        "uq_market_settings_org_market",
        "market_settings",
        ["organization_id", "market_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_market_settings_org_market", table_name="market_settings")
    op.drop_table("market_settings")
