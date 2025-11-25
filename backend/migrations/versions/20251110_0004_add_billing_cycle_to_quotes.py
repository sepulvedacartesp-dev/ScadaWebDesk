"""Agregar columna billing_cycle a quotes

Revision ID: 20251110_0004
Revises: 20251104_0003
Create Date: 2025-11-10 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20251110_0004"
down_revision: Union[str, None] = "20251104_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column(
            "billing_cycle",
            sa.Text(),
            nullable=False,
            server_default="monthly",
        ),
    )
    op.create_check_constraint(
        "chk_quotes_billing_cycle",
        "quotes",
        "billing_cycle IN ('monthly','annual')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_quotes_billing_cycle", "quotes", type_="check")
    op.drop_column("quotes", "billing_cycle")
