# Cotizador – Blueprint Inicial

## Objetivo
- Evolucionar el cotizador actual (frontend estático) a un sistema integral que permita crear, guardar, versionar y consultar cotizaciones ligadas a cada empresa (`empresaId`), con generación de PDF y capacidad de auditoría.

## Estados y Flujo Operativo
- Estados propuestos: `borrador` → `enviada` → (`aceptada` | `anulada`) con expiración automática a los 30 días.
- Transiciones válidas:
  - `borrador` ⇄ `enviada` (permitir correcciones antes de aceptación).
  - `enviada` → `aceptada` (bloquea edición).
  - `enviada` → `anulada` (mantiene historial).
  - Expiración automática mueve `enviada` a `expirada`.
- Registra cambios con bitácora (`quote_events`) para saber quién modificó qué y cuándo.

## Catálogo de Servicios y Precios
- Mantener catálogo en base de datos (`quote_catalog` + `quote_catalog_items`), editable solo por administradores maestros.
- Guardar vigencia (`valid_from`, `valid_to`) para cambios futuros sin redeploy.
- En la cotización almacenar copia de los valores usados (UF y notas) para preservar contexto histórico.

## Datos Mínimos de la Cotización
- Cliente: `cliente_nombre`, `cliente_rut` (validado), `contacto`, `correo`, `telefono`.
- Cotización: `prepared_by`, `prepared_email`, `subtotal_uf`, `descuento_pct`, `neto_uf`, `iva_uf`, `total_uf`, `uf_valor_clp` (opcional), `vigencia_hasta`, `observaciones`.
- Items: `descripcion`, `cantidad`, `precio_unitario_uf`, `nota`, `orden`.
- Campos audit: `created_at`, `updated_at`, `created_by_uid`, `last_updated_by_uid`.

## Numeración y PDF
- Secuencia por empresa: `SUR-{empresaId}-{año}-{correlativo de 3 dígitos}` almacenada en `quote_number`.
- El PDF debe mostrar logo, folio, fecha emisión, vigencia, estado actual y nota legal estándar.
- Generación:
  - Frontend sigue usando jsPDF para previsualizar.
  - Backend almacena representación binaria o JSON de la cotización para reproducir PDF bajo demanda.

## Roles y Permisos
- `quote_admin`: crear, editar, enviar, aceptar, anular.
- `quote_viewer`: lectura y descarga de PDF.
- Usar claims existentes (`CONFIG_ADMIN_EMAILS`) para mapear a `quote_admin`; permitir asignar `quote_viewer` por empresa en `scada_config`.
- Administradores maestros (`MASTER_ADMIN_EMAILS`) pueden ver todas las empresas, modificar catálogo y numeración.

## Infraestructura en Render
- Reutilizar PostgreSQL actual; agregar migraciones con Alembic (worker o hook de deploy).
- Guardar documentos:
  - Volumen esperado (<100/año) permite almacenar PDFs como `bytea` o archivos locales rotados cada 6 meses.
  - Opción futura: mover a bucket S3-compatible si el tamaño crece.
- Ajustar pool `asyncpg` para evitar bloquear consultas de tendencias (separar `quote_db_pool` hermético).

## Modelo de Datos (Propuesta)
```
quotes (
  id uuid pk,
  empresa_id text not null,
  quote_number text unique per empresa+año,
  estado text check in (...),
  cliente_nombre text,
  cliente_rut text,
  contacto text,
  correo text,
  telefono text,
  prepared_by text,
  prepared_email text,
  subtotal_uf numeric(12,2),
  descuento_pct numeric(5,2),
  neto_uf numeric(12,2),
  iva_uf numeric(12,2),
  total_uf numeric(12,2),
  uf_valor_clp numeric(12,2),
  vigencia_hasta timestamp with time zone,
  observaciones text,
  catalog_snapshot jsonb,
  pdf_blob bytea (nullable),
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  created_by_uid text,
  updated_by_uid text
)

quote_items (
  id uuid pk,
  quote_id uuid fk references quotes on delete cascade,
  descripcion text,
  cantidad integer,
  precio_unitario_uf numeric(12,2),
  total_uf numeric(12,2),
  nota text,
  orden integer
)

quote_events (
  id uuid pk,
  quote_id uuid fk references quotes on delete cascade,
  empresa_id text,
  evento text, -- created, updated, status_changed, pdf_downloaded
  descripcion text,
  metadata jsonb,
  created_at timestamp with time zone default now(),
  actor_uid text,
  actor_email text
)
```

## API de Cotizaciones
- `POST /api/quotes` – crea cotización; asigna número secuencial y retorna detalle.
- `GET /api/quotes` – lista paginada, filtros por `estado`, `cliente`, `rut`, `quoteNumber`, rangos de fecha; maestros pueden filtrar por `empresaId`.
- `GET /api/quotes/{id}` – detalle completo con items y eventos.
- `PUT /api/quotes/{id}` – actualiza datos en `borrador` o `enviada`.
- `PATCH /api/quotes/{id}/status` – transiciones controladas (`enviada`, `aceptada`, `anulada`).
- `GET /api/quotes/{id}/pdf` – entrega PDF actual (re-generado o almacenado).
- `GET /api/quote-catalog` / `PUT /api/quote-catalog` – mantenimiento para admins maestros.
- `GET /api/clients`, `POST /api/clients` (opcional) – maestro de clientes para autocompletar.

## UX y Funcionalidades
- Mantener vanilla JS modular:
  - Panel izquierdo: listado con filtros (estado, fecha, cliente, rut).
  - Panel derecho: formulario con tabs (datos cliente, servicios, notas).
  - Botones `Guardar borrador`, `Enviar`, `Aceptar`, `Anular`, `Descargar PDF`.
  - Timeline de eventos y badges de estado.
- Mostrar alertas cuando se acerque la expiración (7 días).
- Autocompletar clientes desde catálogo si existe.

## Roadmap de Implementación
1. **Definición**: validar este blueprint con stakeholders y ajustar según feedback.
2. **Infraestructura**: configurar Alembic, crear migraciones iniciales y pruebas de conexión.
3. **Backend**:
   - Nuevos modelos y CRUD `quotes`, `quote_items`, `quote_events`.
   - Servicios de numeración y reglas de estado.
   - Endpoints REST (incluyendo catálogo y clientes).
   - Generación/almacenamiento de PDF (payload JSON + binario opcional).
4. **Frontend**:
   - Refactor `cotizador.html/js` hacia módulos (listado + editor).
   - Integración con endpoints, manejando estados y validaciones.
   - Descarga de PDF via backend y previsualización local.
5. **Testing y QA**:
   - Seed de datos demo, pruebas e2e (crear → enviar → aceptar → descargar).
   - Validación de roles (`quote_admin` vs `quote_viewer`).
6. **Deploy y Monitoreo**:
   - Actualizar `README`, variables de entorno, documentación interna.
   - Seguimiento de uso (contar cotizaciones) y plan de mantenimiento anual (purga/backup).

## Próximos Pasos
- Revisar y corregir el blueprint según observaciones de negocio.
- Priorizar funcionalidades de la primera versión (MVP) para estimar esfuerzo.
