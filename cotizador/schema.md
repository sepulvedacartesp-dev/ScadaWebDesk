# Cotizador – Esquema y Migraciones

## Estrategia de Migraciones
- Usar **Alembic** con configuración en `backend/migrations`.
- Primera revisión (`20250101_0001_initial_quotes`):
  - Crear tablas `quotes`, `quote_items`, `quote_events`, `quote_catalog`, `quote_catalog_items`, `clients`.
  - Añadir índices multi-columna para búsquedas frecuentes.
  - Configurar secuencia `quote_sequence_{empresaId}_{anio}` manejada vía función helper (no en DB).
- Migraciones posteriores:
  - `20250101_0002_catalog_seed`: insertar catálogo base (contenedores, nexbox, internet, soporte).
  - `20250101_0003_clients_seed` (opcional): clientes demo.
  - Mantener versiones sincronizadas con docs en `cotizador/`.

## DDL Propuesto (PostgreSQL)
```sql
CREATE TABLE quotes (
  id UUID PRIMARY KEY,
  empresa_id TEXT NOT NULL,
  quote_number TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('borrador','enviada','aceptada','anulada','expirada')),
  cliente_nombre TEXT NOT NULL,
  cliente_rut TEXT NOT NULL,
  contacto TEXT,
  correo TEXT,
  telefono TEXT,
  prepared_by TEXT,
  prepared_email TEXT,
  subtotal_uf NUMERIC(12,2) NOT NULL DEFAULT 0,
  descuento_pct NUMERIC(5,2) NOT NULL DEFAULT 0,
  neto_uf NUMERIC(12,2) NOT NULL DEFAULT 0,
  iva_uf NUMERIC(12,2) NOT NULL DEFAULT 0,
  total_uf NUMERIC(12,2) NOT NULL DEFAULT 0,
  uf_valor_clp NUMERIC(12,2),
  vigencia_hasta TIMESTAMP WITH TIME ZONE,
  observaciones TEXT,
  catalog_snapshot JSONB,
  pdf_blob BYTEA,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by_uid TEXT,
  updated_by_uid TEXT,
  UNIQUE (empresa_id, quote_number)
);

CREATE INDEX idx_quotes_empresa_estado ON quotes (empresa_id, estado);
CREATE INDEX idx_quotes_cliente ON quotes (empresa_id, cliente_rut);
CREATE INDEX idx_quotes_created_at ON quotes (empresa_id, created_at DESC);

CREATE TABLE quote_items (
  id UUID PRIMARY KEY,
  quote_id UUID NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
  descripcion TEXT NOT NULL,
  cantidad INTEGER NOT NULL CHECK (cantidad >= 0),
  precio_unitario_uf NUMERIC(12,2) NOT NULL,
  total_uf NUMERIC(12,2) NOT NULL,
  nota TEXT,
  orden INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_quote_items_quote ON quote_items (quote_id, orden);

CREATE TABLE quote_events (
  id UUID PRIMARY KEY,
  quote_id UUID NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
  empresa_id TEXT NOT NULL,
  evento TEXT NOT NULL,
  descripcion TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  actor_uid TEXT,
  actor_email TEXT
);

CREATE INDEX idx_quote_events_quote ON quote_events (quote_id, created_at DESC);

CREATE TABLE quote_catalog (
  id UUID PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  descripcion TEXT,
  tipo TEXT NOT NULL DEFAULT 'service',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  activo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE quote_catalog_items (
  id UUID PRIMARY KEY,
  catalog_id UUID NOT NULL REFERENCES quote_catalog(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  valor_uf NUMERIC(12,2) NOT NULL,
  nota TEXT,
  orden INTEGER NOT NULL DEFAULT 0,
  valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
  valid_to DATE
);

CREATE INDEX idx_quote_catalog_items_catalog ON quote_catalog_items (catalog_id, valid_from DESC);

CREATE TABLE clients (
  id UUID PRIMARY KEY,
  empresa_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  rut TEXT NOT NULL,
  contacto TEXT,
  correo TEXT,
  telefono TEXT,
  notas TEXT,
  UNIQUE (empresa_id, rut)
);
```

## Contratos de API (Borrador JSON)

### POST /api/quotes
```json
Request {
  "empresaId": "auto (derivado del token)",
  "cliente": {
    "nombre": "SurNex Energías",
    "rut": "76.543.210-3",
    "contacto": "Juan Pérez",
    "correo": "juan@cliente.cl",
    "telefono": "+56 9 1234 5678"
  },
  "preparedBy": "Administrador",
  "items": [
    {
      "catalogSlug": "container",
      "descripcion": "Contenedor principal",
      "cantidad": 1,
      "precioUF": 3.16,
      "nota": "Incluye instalación"
    }
  ],
  "descuentoPct": 0,
  "ufValorClp": 36000,
  "vigenciaDias": 30,
  "observaciones": "Cotización válida por 30 días"
}

Response {
  "id": "uuid",
  "quoteNumber": "SUR-demo-2025-001",
  "estado": "borrador",
  "createdAt": "2025-01-01T12:00:00Z",
  "items": [...],
  "totales": {
    "subtotalUF": 3.16,
    "descuentoUF": 0,
    "netoUF": 3.16,
    "ivaUF": 0.6,
    "totalUF": 3.76
  }
}
```

### GET /api/quotes?estado=enviada&cliente=sur
- Respuesta paginada:
```json
{
  "results": [
    {
      "id": "uuid",
      "quoteNumber": "SUR-demo-2025-001",
      "clienteNombre": "SurNex Energías",
      "clienteRut": "76.543.210-3",
      "estado": "enviada",
      "totalUF": 3.76,
      "vigenciaHasta": "2025-02-01T00:00:00Z",
      "createdAt": "2025-01-01T12:00:00Z"
    }
  ],
  "page": 1,
  "pageSize": 20,
  "total": 1
}
```

### PATCH /api/quotes/{id}/status
```json
Request { "estado": "aceptada" }
Response { "ok": true, "estado": "aceptada", "updatedAt": "2025-01-05T10:30:00Z" }
```

### GET /api/quotes/{id}/pdf
- Devuelve `application/pdf`.
- Acepta parámetro `?refresh=1` para regenerar desde snapshot si no hay blob almacenado.

### Catalog API
- `GET /api/quote-catalog`: lista categorías y items activos.
- `PUT /api/quote-catalog`: solo maestros, permite alta/baja/actualizaciones.

### Clients API (opcional)
- `GET /api/clients?query=sur`: autocompletado.
- `POST /api/clients`: creación rápida desde cotizador.

## Consideraciones de Seguridad
- Todos los endpoints requieren token Firebase.
- Filtrado por `empresaId` derivado del token salvo usuarios maestro.
- Log de eventos en `quote_events` cada vez que se crea/actualiza/descarga PDF.
- Sanitizar inputs (RUT, emails) y aplicar límites (máx. 100 items por cotización).
