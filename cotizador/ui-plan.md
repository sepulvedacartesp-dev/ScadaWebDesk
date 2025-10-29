# Cotizador Fase 2 – Plan de UI/UX

## Objetivo
Transformar `cotizador.html/js` en una mini‑aplicación con:
- Listado de cotizaciones con filtros.
- Editor/visor de detalle (crear/editar).
- Integración con los endpoints REST (`/api/quotes`, `/api/quote-catalog`, `/api/clients`).
- Manejo de permisos y estados (botones según rol/status).

## Flujo de Usuario
1. **Listado inicial**: muestra las cotizaciones más recientes, ordenadas por fecha de creación.
2. **Filtros**: estado (chips), rango de fechas, búsqueda (cliente/folio), RUT.
3. **Acciones en listado**:
   - Seleccionar una fila → carga detalle en panel derecho.
   - Botón “Nueva cotización” → limpia formulario en modo creación.
4. **Editor**:
   - Sección Datos cliente (autocompletar por RUT o nombre).
   - Tabla de ítems (con filas dinámicas) precargada con catálogo.
   - Totales calculados en vivo (UF + CLP opcional).
   - Botones según estado:
     - `Guardar borrador`, `Enviar`, `Aceptar`, `Anular`, `Descargar PDF`.
   - Timeline de eventos (mostrado en pestaña o panel inferior).

## Arquitectura Frontend
- Mantener vanilla JS pero modular:
  - `cotizador/api.js`: peticiones fetch con token.
  - `cotizador/store.js`: estado en memoria (cotizaciones, catálogo, cliente seleccionado).
  - `cotizador/list-view.js`: render del listado + filtros.
  - `cotizador/editor.js`: formulario y lógica de cálculos.
  - `cotizador/events.js`: timeline y logs.
- `index.html` seguirá cargando `cotizador.js` como entry point, que importará los módulos anteriores.
- Uso de eventos personalizados para coordinar cambios entre paneles.

## Estructura de Layout
- **Header** (ya existente) + botón “Nueva cotización”.
- **Split view** (flex):
  - Columna izquierda (~40% width) -> listado + filtros + paginación simple.
  - Columna derecha (~60% width) -> editor + tabs (“Detalle”, “Eventos”).
- Responsivo: en pantallas pequeñas, listado arriba, editor debajo (tabs).

## Reutilización de datos
- Al iniciar:
  1. `GET /api/quote-catalog` -> guardar catálogo y notas.
  2. `GET /api/quotes` (page=1) -> render listado.
- Autocomplete cliente: `GET /api/clients?q=xxx`.
- Previo a enviar estado → `PATCH /api/quotes/{id}/status`.
- PDF: todavía usa jsPDF localmente, pero registra descarga con `POST /api/quotes/{id}/events/pdf`.

## Estados y Validaciones
- Deshabilitar edición si estado en `aceptada/anulada/expirada`.
- Mostrar confirmación antes de cambiar estado (modal simple).
- Mostrar alertas de error con `alert()` temporal y plan para UI custom (toast).

## Próximos Pasos
1. Refactor `cotizador.js` en módulos y preparar entry (`cotizador/main.js`).
2. Implementar capa API (`fetch` + manejo de errores/401) y store.
3. Construir listado + filtros (usar template literal o DOM).
4. Construir editor con ítems dinámicos y totales.
5. Integrar estado -> timeline + acciones.
6. Ajustar estilos (posiblemente nueva hoja `cotizador.css`).
