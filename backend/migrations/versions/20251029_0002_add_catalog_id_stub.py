"""compatibility stub to preserve revision 20251029_0002

Revision ID: 20251029_0002
Revises: 20250101_0001
Create Date: 2025-10-29 00:00:00.000000
"""

from __future__ import annotations


revision = "20251029_0002"
down_revision = "20250101_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op migration kept for historical compatibility."""
    pass


def downgrade() -> None:
    pass

