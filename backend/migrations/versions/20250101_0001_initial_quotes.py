"""Crear tablas base para Cotizador

Revision ID: 20250101_0001
Revises: 
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20250101_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("empresa_id", sa.Text(), nullable=False),
        sa.Column("quote_number", sa.Text(), nullable=False),
        sa.Column(
            "estado",
            sa.Text(),
            nullable=False,
            server_default="borrador",
        ),
        sa.Column("cliente_nombre", sa.Text(), nullable=False),
        sa.Column("cliente_rut", sa.Text(), nullable=False),
        sa.Column("contacto", sa.Text()),
        sa.Column("correo", sa.Text()),
        sa.Column("telefono", sa.Text()),
        sa.Column("prepared_by", sa.Text()),
        sa.Column("prepared_email", sa.Text()),
        sa.Column("subtotal_uf", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("descuento_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("neto_uf", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("iva_uf", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_uf", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("uf_valor_clp", sa.Numeric(12, 2)),
        sa.Column("vigencia_hasta", sa.TIMESTAMP(timezone=True)),
        sa.Column("observaciones", sa.Text()),
        sa.Column("catalog_snapshot", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("pdf_blob", sa.LargeBinary()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("created_by_uid", sa.Text()),
        sa.Column("updated_by_uid", sa.Text()),
        sa.CheckConstraint(
            "estado IN ('borrador','enviada','aceptada','anulada','expirada')",
            name="chk_quotes_estado",
        ),
        sa.UniqueConstraint("empresa_id", "quote_number", name="uq_quotes_empresa_quote_number"),
        sa.CheckConstraint("subtotal_uf >= 0", name="chk_quotes_subtotal"),
        sa.CheckConstraint("descuento_pct >= 0", name="chk_quotes_descuento_pct_min"),
        sa.CheckConstraint("descuento_pct <= 100", name="chk_quotes_descuento_pct_max"),
        sa.CheckConstraint("neto_uf >= 0", name="chk_quotes_neto"),
        sa.CheckConstraint("iva_uf >= 0", name="chk_quotes_iva"),
        sa.CheckConstraint("total_uf >= 0", name="chk_quotes_total"),
    )
    op.create_index("idx_quotes_empresa_estado", "quotes", ["empresa_id", "estado"])
    op.create_index("idx_quotes_cliente", "quotes", ["empresa_id", "cliente_rut"])
    op.create_index("idx_quotes_created_at", "quotes", ["empresa_id", "created_at"])

    op.create_table(
        "quote_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("tipo", sa.Text(), nullable=False, server_default="service"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
    )

    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("empresa_id", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("rut", sa.Text(), nullable=False),
        sa.Column("contacto", sa.Text()),
        sa.Column("correo", sa.Text()),
        sa.Column("telefono", sa.Text()),
        sa.Column("notas", sa.Text()),
        sa.UniqueConstraint("empresa_id", "rut", name="uq_clients_empresa_rut"),
    )

    op.create_table(
        "quote_catalog_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("valor_uf", sa.Numeric(12, 2), nullable=False),
        sa.Column("nota", sa.Text()),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("valid_to", sa.Date()),
        sa.ForeignKeyConstraint(
            ["catalog_id"],
            ["quote_catalog.id"],
            name="fk_quote_catalog_items_catalog",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("valor_uf >= 0", name="chk_quote_catalog_items_valor"),
        sa.CheckConstraint("orden >= 0", name="chk_quote_catalog_items_orden"),
    )
    op.create_index(
        "idx_quote_catalog_items_catalog",
        "quote_catalog_items",
        ["catalog_id", "valid_from"],
    )

    op.create_table(
        "quote_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("precio_unitario_uf", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_uf", sa.Numeric(12, 2), nullable=False),
        sa.Column("nota", sa.Text()),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            name="fk_quote_items_quote",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("cantidad >= 0", name="chk_quote_items_cantidad"),
        sa.CheckConstraint("precio_unitario_uf >= 0", name="chk_quote_items_precio"),
        sa.CheckConstraint("total_uf >= 0", name="chk_quote_items_total"),
        sa.CheckConstraint("orden >= 0", name="chk_quote_items_orden"),
    )
    op.create_index("idx_quote_items_quote", "quote_items", ["quote_id", "orden"])

    op.create_table(
        "quote_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("empresa_id", sa.Text(), nullable=False),
        sa.Column("evento", sa.Text(), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("actor_uid", sa.Text()),
        sa.Column("actor_email", sa.Text()),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            name="fk_quote_events_quote",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_quote_events_quote", "quote_events", ["quote_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_quote_events_quote", table_name="quote_events")
    op.drop_table("quote_events")
    op.drop_index("idx_quote_items_quote", table_name="quote_items")
    op.drop_table("quote_items")
    op.drop_index("idx_quote_catalog_items_catalog", table_name="quote_catalog_items")
    op.drop_table("quote_catalog_items")
    op.drop_table("clients")
    op.drop_table("quote_catalog")
    op.drop_index("idx_quotes_created_at", table_name="quotes")
    op.drop_index("idx_quotes_cliente", table_name="quotes")
    op.drop_index("idx_quotes_empresa_estado", table_name="quotes")
    op.drop_table("quotes")
