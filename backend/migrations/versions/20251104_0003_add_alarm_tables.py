"""add alarm rules and events tables

Revision ID: 20251104_0003
Revises: 20251029_0002_add_catalog_id_to_quote_items
Create Date: 2025-11-04 18:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251104_0003"
down_revision = "20251029_0002_add_catalog_id_to_quote_items"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "alarm_rules",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("empresa_id", sa.Text, nullable=False),
        sa.Column("tag", sa.Text, nullable=False),
        sa.Column("operator", sa.Text, nullable=False),
        sa.Column("threshold_value", sa.Float, nullable=False),
        sa.Column("value_type", sa.Text, nullable=False),
        sa.Column("notify_email", sa.Text, nullable=False),
        sa.Column("cooldown_seconds", sa.Integer, nullable=False, server_default="300"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_triggered_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint("operator IN ('lte', 'gte', 'eq')", name="ck_alarm_rules_operator"),
        sa.CheckConstraint("value_type IN ('number', 'boolean')", name="ck_alarm_rules_value_type"),
    )
    op.create_index(
        "ix_alarm_rules_empresa_tag_active",
        "alarm_rules",
        ["empresa_id", "tag", "active"],
    )

    op.create_table(
        "alarm_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("rule_id", sa.BigInteger, sa.ForeignKey("alarm_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Text, nullable=False),
        sa.Column("tag", sa.Text, nullable=False),
        sa.Column("observed_value", sa.Float, nullable=False),
        sa.Column("operator", sa.Text, nullable=False),
        sa.Column("threshold_value", sa.Float, nullable=False),
        sa.Column("email_sent", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("email_error", sa.Text, nullable=True),
        sa.Column("triggered_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("notified_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_alarm_events_empresa_tag_triggered_at",
        "alarm_events",
        ["empresa_id", "tag", "triggered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_alarm_events_empresa_tag_triggered_at", table_name="alarm_events")
    op.drop_table("alarm_events")
    op.drop_index("ix_alarm_rules_empresa_tag_active", table_name="alarm_rules")
    op.drop_table("alarm_rules")

