# Cotizador – Backlog y Roadmap

## Visión General
- MVP enfocado en registrar y gestionar hasta 100 cotizaciones anuales, con auditoría básica y restricción por empresa.
- Release incremental para minimizar riesgo: primero backend/migraciones, luego frontend y PDF.

## Hitos Principales
1. **Fundación de Datos**
   - Configurar Alembic dentro de `backend` (script `alembic.ini`, carpeta `migrations`).
   - Crear migración inicial con tablas `quotes`, `quote_items`, `quote_events`, `quote_catalog`, `quote_catalog_items`, `clients` (opcional con flag).
   - Añadir fixtures de catálogo y cliente demo.

2. **Servicios Backend**
   - Pool dedicado (`quote_db_pool`) y helpers DAO.
   - Endpoints REST (`/api/quotes`, `/api/quote-catalog`, `/api/clients`).
   - Validaciones de estado y numeración secuencial.
   - Almacenamiento del snapshot de catálogo usado y bitácora de eventos.
   - Endpoint para PDF (`GET /api/quotes/{id}/pdf`) que re-renderice a partir del snapshot.

3. **Frontend Cotizador**
   - Refactor `cotizador.html/js` a módulos: listado + editor + timeline.
   - Integración con APIs (fetch, filtros, paginado simple).
   - Formularios con validaciones de RUT, correo y teléfonos.
   - Generación/descarga de PDF contra el endpoint backend; previsualización opcional.

4. **Control de Acceso y Roles**
   - Mapear claims `quote_admin` y `quote_viewer` en backend y frontend.
   - Actualizar `script.js` para mostrar funcionalidades según permisos.
   - Ajustar `CONFIG_ADMIN_EMAILS` y documentación para nuevos roles.

5. **QA y Deploy**
   - Tests unitarios backend (validaciones, numeración, reglas de estado).
   - Seed de datos demo y script para limpiar entornos locales.
   - Documentar flujo en README, actualizar Render (build command, env vars).
   - Sesión de pruebas con usuarios finales; checklist de regresión SCADA.

6. **Opciones Futuras**
   - Envío de PDF por correo (hook opcional).
   - Integración con bucket externo para almacenamiento de archivos.
   - Reportes trimestrales y exportación CSV.

## Orden de Trabajo Sugerido
1. Configurar Alembic + migración inicial.
2. Implementar repositorios/servicios del backend (sin endpoints).
3. Exponer endpoints REST y validar con Swagger o tests.
4. Refactor frontend y conectar con backend.
5. Añadir generación de PDF backend + pruebas integradas.
6. Documentar, preparar despliegue y realizar pruebas end-to-end.
