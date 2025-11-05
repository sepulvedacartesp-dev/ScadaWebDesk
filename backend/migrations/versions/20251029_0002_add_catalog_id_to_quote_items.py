"""placeholder to preserve migration chain for quote catalog id

Revision ID: 20251029_0002_add_catalog_id_to_quote_items
Revises: 20250101_0001
Create Date: 2025-10-29 00:00:00.000000
"""

from __future__ import annotations

from alembic import op  # noqa: F401


revision = "20251029_0002_add_catalog_id_to_quote_items"
down_revision = "20250101_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:  # noqa: D401
    """No structural changes required; migration retained for compatibility."""
    # El esquema actual ya incluye catalog_id en quote_items desde la revision inicial.
    # Este archivo se mantiene para enlazar la cadena historica de migraciones.
    pass


def downgrade() -> None:
    pass

