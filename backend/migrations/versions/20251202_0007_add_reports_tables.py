"""add report_definitions and report_runs tables

Revision ID: 20251202_0007
Revises: 20251126_0006
Create Date: 2025-12-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251202_0007"
down_revision = "20251126_0006"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "report_definitions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("empresa_id", sa.Text(), nullable=False),
        sa.Column("planta_id", sa.Text(), nullable=False, server_default="default"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("frequency", sa.Text(), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=True),
        sa.Column("day_of_month", sa.SmallInteger(), nullable=True),
        sa.Column("time_of_day", sa.Time(timezone=False), nullable=True, server_default=sa.text("'08:00:00'")),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.Column("include_alarms", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("send_email", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("format", sa.Text(), nullable=False, server_default="pdf"),
        sa.Column("recipients", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("slot", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("frequency IN ('daily', 'weekly', 'monthly')", name="ck_report_def_frequency"),
        sa.CheckConstraint("(slot >= 1) AND (slot <= 2)", name="ck_report_def_slot_range"),
        sa.CheckConstraint(
            "(frequency <> 'weekly') OR (day_of_week BETWEEN 1 AND 7)", name="ck_report_def_weekly_day"
        ),
        sa.CheckConstraint(
            "(frequency <> 'monthly') OR (day_of_month BETWEEN 1 AND 31)", name="ck_report_def_monthly_day"
        ),
    )
    op.create_index(
        "ix_report_def_empresa_planta",
        "report_definitions",
        ["empresa_id", "planta_id"],
    )
    op.create_index(
        "uq_report_def_empresa_planta_slot",
        "report_definitions",
        ["empresa_id", "planta_id", "slot"],
        unique=True,
    )

    op.create_table(
        "report_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.BigInteger(),
            sa.ForeignKey("report_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("empresa_id", sa.Text(), nullable=False),
        sa.Column("planta_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("send_email", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("emails_sent", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("pdf_size_bytes", sa.Integer(), nullable=True),
        sa.Column("pdf_mime", sa.Text(), nullable=True, server_default=sa.text("'application/pdf'")),
        sa.Column("pdf_blob", sa.LargeBinary(), nullable=True),
        sa.Column("triggered_by", sa.Text(), nullable=True),
    )
    op.create_index("ix_report_runs_report", "report_runs", ["report_id"])
    op.create_index("ix_report_runs_empresa_status", "report_runs", ["empresa_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_report_runs_empresa_status", table_name="report_runs")
    op.drop_index("ix_report_runs_report", table_name="report_runs")
    op.drop_table("report_runs")

    op.drop_index("uq_report_def_empresa_planta_slot", table_name="report_definitions")
    op.drop_index("ix_report_def_empresa_planta", table_name="report_definitions")
    op.drop_table("report_definitions")
