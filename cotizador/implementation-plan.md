# Plan de Implementación – Cotizador

## Fase 0 – Preparación (1-2 días)
- Instalar Alembic en el entorno backend; actualizar `requirements.txt`.
- Configurar `alembic.ini`, carpeta `migrations/` y script de arranque en Render.
- Crear migración inicial (`20250101_0001_initial_quotes`).
- Añadir script de seeds (catálogo base y cliente demo) ejecutable vía `python -m backend.scripts.seed_quotes`.
- Actualizar README con pasos de setup (migraciones, seeds, variables nuevas).

## Fase 1 – Backend Core (3-4 días)
- Implementar módulo `quotes/service.py` con:
  - Reglas de numeración por `empresaId` + año.
  - Validación de estados y caducidad automática (tarea cron opcional).
  - Persistencia de `quote_items` y snapshot de catálogo.
- Crear routers FastAPI:
  - `quotes_router` (`POST`, `GET`, `PUT`, `PATCH`, `GET /pdf`).
  - `catalog_router`, `clients_router` (si se activa catálogo de clientes).
- Middleware de permisos: mapear `quote_admin` / `quote_viewer` según claims existentes.
- Tests unitarios/integ (pytest) para servicios y endpoints críticos.

## Fase 2 – Frontend (3-4 días)
- Organizar `cotizador.html/js` en módulos ES6 (`cotizador/list.js`, `cotizador/editor.js`, `cotizador/api.js`).
- Crear layout maestro: listado (tabla) + filtros (estado, cliente, RUT, fecha) + editor lateral.
- Conectar llamadas a API (fetch con token Firebase).
- Validaciones de formularios (RUT, e-mail, números) y mensajes de error accesibles.
- Generar PDF consultando endpoint backend; permitir descarga directa.
- Componentes UI: timeline de eventos, badges de estado, botones de acción según permisos.

## Fase 3 – QA y Deploy (2 días)
- Scripts de seed para entorno de prueba en Render.
- Checklist E2E:
  - Crear borrador, guardar, enviar, aceptar/anular.
  - Buscar por cliente/RUT/estado.
  - Descargar PDF y validar folio.
  - Verificar restricción de permisos (`quote_viewer` sin botones de edición).
- Documentar manual de uso (paso a paso) y actualizar `cotizador/definitions.md` con cualquier ajuste final.
- Preparar changelog y comunicar a usuarios finales.

## Riesgos y Mitigaciones
- **Concurrencia en numeración**: usar transacción serializable o `FOR UPDATE` al generar folio.
- **Crecimiento del PDF**: si excede límites, activar almacenamiento en S3 más adelante.
- **Timeouts en Render**: limitar consultas paginadas a 100 filas y usar índices definidos.

## Dependencias Externas
- Firebase Authentication (tokens válidos).
- PostgreSQL (acceso desde Render + local).
- Herramientas de correo (futuro); dejar interfaz lista.

## Métricas de Éxito
- Cotizaciones se pueden recuperar y editar 100% desde el sistema.
- Generación de PDF consistente con folio y snapshot.
- Usuarios con rol viewer no pueden modificar cotizaciones.
- Tiempo de respuesta < 1s para búsquedas normales (<50 resultados).
