"""add planta_id to trends and alarms tables

Revision ID: 20251125_0005
Revises: 20251110_0004
Create Date: 2025-11-25 16:50:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251125_0005"
down_revision = "20251110_0004"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # trends: add planta_id and rebuild index
    op.execute("ALTER TABLE trends ADD COLUMN IF NOT EXISTS planta_id TEXT NOT NULL DEFAULT 'default'")
    op.execute("DROP INDEX IF EXISTS trends_empresa_tag_ts_idx")
    op.create_index(
        "trends_empresa_planta_tag_ts_idx",
        "trends",
        ["empresa_id", "planta_id", "tag", sa.text("timestamp DESC")],
    )

    # alarm_rules: add planta_id and adjust index
    op.execute("ALTER TABLE alarm_rules ADD COLUMN IF NOT EXISTS planta_id TEXT NOT NULL DEFAULT 'default'")
    op.execute("DROP INDEX IF EXISTS ix_alarm_rules_empresa_tag_active")
    op.create_index(
        "ix_alarm_rules_empresa_planta_tag_active",
        "alarm_rules",
        ["empresa_id", "planta_id", "tag", "active"],
    )

    # alarm_events: add planta_id and adjust index
    op.execute("ALTER TABLE alarm_events ADD COLUMN IF NOT EXISTS planta_id TEXT NOT NULL DEFAULT 'default'")
    op.execute("DROP INDEX IF EXISTS ix_alarm_events_empresa_tag_triggered_at")
    op.create_index(
        "ix_alarm_events_empresa_planta_tag_triggered_at",
        "alarm_events",
        ["empresa_id", "planta_id", "tag", sa.text("triggered_at DESC")],
    )


def downgrade() -> None:
    # alarm_events: restore previous index and drop planta_id
    op.drop_index("ix_alarm_events_empresa_planta_tag_triggered_at", table_name="alarm_events")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alarm_events_empresa_tag_triggered_at ON alarm_events (empresa_id, tag, triggered_at)")
    op.execute("ALTER TABLE alarm_events DROP COLUMN IF EXISTS planta_id")

    # alarm_rules: restore previous index and drop planta_id
    op.drop_index("ix_alarm_rules_empresa_planta_tag_active", table_name="alarm_rules")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alarm_rules_empresa_tag_active ON alarm_rules (empresa_id, tag, active)")
    op.execute("ALTER TABLE alarm_rules DROP COLUMN IF EXISTS planta_id")

    # trends: restore previous index and drop planta_id
    op.drop_index("trends_empresa_planta_tag_ts_idx", table_name="trends")
    op.execute("CREATE INDEX IF NOT EXISTS trends_empresa_tag_ts_idx ON trends (empresa_id, tag, timestamp DESC)")
    op.execute("ALTER TABLE trends DROP COLUMN IF EXISTS planta_id")
