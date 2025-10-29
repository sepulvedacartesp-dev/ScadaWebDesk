"""Add catalog_id column to quote_items

Revision ID: 20251029_0002
Revises: 20250101_0001
Create Date: 2025-10-29 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20251029_0002"
down_revision: Union[str, None] = "20250101_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quote_items",
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quote_items_catalog",
        "quote_items",
        "quote_catalog",
        ["catalog_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_quote_items_catalog", "quote_items", type_="foreignkey")
    op.drop_column("quote_items", "catalog_id")

