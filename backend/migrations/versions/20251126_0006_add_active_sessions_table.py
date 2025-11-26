"""add active_sessions table for ws session tracking

Revision ID: 20251126_0006
Revises: 20251125_0005
Create Date: 2025-11-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251126_0006"
down_revision = "20251125_0005"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "active_sessions" not in existing_tables:
        op.create_table(
            "active_sessions",
            sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("empresa_id", sa.Text(), nullable=False),
            sa.Column("uid", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("active_sessions")} if "active_sessions" in existing_tables else set()
    if "active_sessions_empresa_idx" not in existing_indexes:
        op.create_index("active_sessions_empresa_idx", "active_sessions", ["empresa_id"])


def downgrade() -> None:
    op.drop_index("active_sessions_empresa_idx", table_name="active_sessions")
    op.drop_table("active_sessions")
