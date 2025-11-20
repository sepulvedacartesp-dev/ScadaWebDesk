import {
  fetchQuoteCatalog,
  listQuotes,
  getQuote,
  createQuote,
  updateQuote,
  changeQuoteStatus,
  listClients,
  createClient,
  logQuotePdfDownload,
} from "./api.js";
import { downloadQuotePdf } from "./pdf.js";

const state = {
  catalogCategories: [],
  catalogItems: [],
  quotes: [],
  pagination: { page: 1, pageSize: 10, total: 0 },
  filters: { search: "", estado: "", clienteRut: "" },
  selectedQuoteId: null,
  selectedQuote: null,
  editingItems: [],
  loadingList: false,
  loadingDetail: false,
};

const dom = {};
const STATUS_LABELS = {
  borrador: "Borrador",
  enviada: "Enviada",
  aceptada: "Aceptada",
  anulada: "Anulada",
  expirada: "Expirada",
};

window.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  cacheDom();
  bindEvents();
  ensurePaneExpanded("list");
  ensurePaneExpanded("detail");
  toggleDetail(false);
  await loadCatalog();
  await loadQuotes();
}

function cacheDom() {
  dom.newQuoteBtn = document.getElementById("new-quote-btn");
  dom.applyFiltersBtn = document.getElementById("apply-filters-btn");
  dom.clearFiltersBtn = document.getElementById("clear-filters-btn");
  dom.filtersForm = document.getElementById("filters-form");
  dom.filterSearch = document.getElementById("filter-search");
  dom.filterStatus = document.getElementById("filter-status");
  dom.filterRut = document.getElementById("filter-rut");
  dom.quoteTable = document.getElementById("quote-table");
  dom.quoteTableBody = dom.quoteTable.querySelector("tbody");
  dom.quoteEmptyState = document.getElementById("quote-empty-state");
  dom.paginationInfo = document.getElementById("pagination-info");
  dom.prevPageBtn = document.getElementById("prev-page-btn");
  dom.nextPageBtn = document.getElementById("next-page-btn");
  dom.detailContainer = document.getElementById("quote-detail");
  dom.detailPlaceholder = document.getElementById("detail-placeholder");
  dom.detailTitle = document.getElementById("detail-title");
  dom.detailSubtitle = document.getElementById("detail-subtitle");
  dom.detailForm = document.getElementById("quote-detail-form");
  dom.quoteId = document.getElementById("quote-id");
  dom.clientName = document.getElementById("client-name");
  dom.clientRut = document.getElementById("client-rut");
  dom.clientContact = document.getElementById("client-contact");
  dom.clientEmail = document.getElementById("client-email");
  dom.clientPhone = document.getElementById("client-phone");
  dom.clientSearchBtn = document.getElementById("client-search-btn");
  dom.clientSaveBtn = document.getElementById("client-save-btn");
  dom.itemsTable = document.getElementById("items-table");
  dom.itemsBody = dom.itemsTable.querySelector("tbody");
  dom.addItemBtn = document.getElementById("add-item-btn");
  dom.preparedBy = document.getElementById("prepared-by");
  dom.preparedEmail = document.getElementById("prepared-email");
  dom.discountPercent = document.getElementById("discount-percent");
  dom.ufValue = document.getElementById("uf-value");
  dom.validityDays = document.getElementById("validity-days");
  dom.quoteNotes = document.getElementById("quote-notes");
  dom.totals = {
    subtotal: document.getElementById("totals-subtotal"),
    discount: document.getElementById("totals-discount"),
    net: document.getElementById("totals-net"),
    tax: document.getElementById("totals-tax"),
    total: document.getElementById("totals-total"),
  };
  dom.saveBtn = document.getElementById("save-quote-btn");
  dom.sendBtn = document.getElementById("send-quote-btn");
  dom.acceptBtn = document.getElementById("accept-quote-btn");
  dom.voidBtn = document.getElementById("void-quote-btn");
  dom.downloadBtn = document.getElementById("download-quote-btn");
  dom.timeline = document.getElementById("timeline");
  dom.panes = document.querySelectorAll("[data-pane]");
  dom.paneToggles = Array.from(document.querySelectorAll("[data-toggle-pane]"));
}

function bindEvents() {
  dom.newQuoteBtn?.addEventListener("click", () => {
    startNewQuote();
  });
  dom.applyFiltersBtn?.addEventListener("click", () => {
    applyFilters();
  });
  dom.clearFiltersBtn?.addEventListener("click", () => {
    clearFilters();
  });
  dom.prevPageBtn?.addEventListener("click", () => changePage(-1));
  dom.nextPageBtn?.addEventListener("click", () => changePage(1));
  dom.quoteTableBody?.addEventListener("click", handleTableClick);
  dom.addItemBtn?.addEventListener("click", () => addItem());
  dom.itemsBody?.addEventListener("input", handleItemInput);
  dom.itemsBody?.addEventListener("change", handleItemChange);
  dom.itemsBody?.addEventListener("click", handleItemRemove);
  dom.detailForm?.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  dom.saveBtn?.addEventListener("click", () => saveQuote());
  dom.sendBtn?.addEventListener("click", () => updateStatus("enviada"));
  dom.acceptBtn?.addEventListener("click", () => updateStatus("aceptada"));
  dom.voidBtn?.addEventListener("click", () => updateStatus("anulada"));
  dom.downloadBtn?.addEventListener("click", () => downloadCurrentQuote());
  dom.clientSearchBtn?.addEventListener("click", () => searchClient());
  dom.clientSaveBtn?.addEventListener("click", () => saveClientFromForm());
  dom.discountPercent?.addEventListener("input", () => updateTotals());
  dom.paneToggles?.forEach((btn) => {
    const paneName = btn.getAttribute("data-toggle-pane");
    if (!paneName) return;
    btn.addEventListener("click", () => togglePane(paneName));
    refreshPaneToggle(paneName);
  });
}

async function loadCatalog() {
  try {
    const categories = await fetchQuoteCatalog();
    state.catalogCategories = Array.isArray(categories) ? categories : [];
    state.catalogItems = state.catalogCategories.flatMap((cat) =>
      (cat.items || []).map((item) => ({
        catalogId: cat.id,
        categorySlug: cat.slug,
        itemId: item.id,
        label: item.label,
        valorUF: Number(item.valor_uf ?? 0),
        nota: item.nota || "",
        optionValue: `${cat.id}:${item.id}`,
      }))
    );
  } catch (error) {
    console.error("Error cargando catalogo", error);
    alert("No se pudo cargar el catalogo de servicios.");
    state.catalogCategories = [];
    state.catalogItems = [];
  }
}

async function loadQuotes() {
  setListLoading(true);
  try {
    const response = await listQuotes({
      page: state.pagination.page,
      pageSize: state.pagination.pageSize,
      filters: state.filters,
    });
    const results = Array.isArray(response?.results) ? response.results : [];
    state.quotes = results;
    state.pagination.total = Number(response?.total || results.length);
    state.pagination.page = Number(response?.page || 1);
    state.pagination.pageSize = Number(response?.page_size || state.pagination.pageSize);
    renderQuoteTable();
    updatePagination();
    if (!state.selectedQuoteId && results.length) {
      selectQuote(results[0].id);
    } else if (state.selectedQuoteId) {
      const stillExists = results.some((item) => item.id === state.selectedQuoteId);
      if (!stillExists && results.length) {
        selectQuote(results[0].id);
      } else if (stillExists) {
        highlightSelectedRow();
      }
    }
  } catch (error) {
    console.error("Error listando cotizaciones", error);
    alert(error?.message || "No se pudieron cargar las cotizaciones.");
  } finally {
    setListLoading(false);
  }
}

function renderQuoteTable() {
  const tbody = dom.quoteTableBody;
  if (!tbody) return;
  if (!state.quotes.length) {
    dom.quoteEmptyState?.removeAttribute("hidden");
    tbody.innerHTML = "";
    return;
  }
  dom.quoteEmptyState?.setAttribute("hidden", "hidden");
  const rows = state.quotes
    .map((quote) => {
      const totalUF = Number(quote.total_uf ?? quote.totalUF ?? 0);
      const fecha = formatDateTime(quote.updated_at || quote.created_at);
      const selectedClass = quote.id === state.selectedQuoteId ? "quote-row--selected" : "";
      return `
        <tr class="quote-row ${selectedClass}" data-id="${quote.id}">
          <td>${quote.quote_number || quote.quoteNumber || "--"}</td>
          <td>${quote.cliente_nombre || "--"}</td>
          <td><span class="status-pill" data-status="${quote.estado}">${STATUS_LABELS[quote.estado] || quote.estado}</span></td>
          <td>${formatUF(totalUF)}</td>
          <td>${fecha}</td>
        </tr>
      `;
    })
    .join("");
  tbody.innerHTML = rows;
}

function updatePagination() {
  const totalPages = Math.max(1, Math.ceil(state.pagination.total / state.pagination.pageSize));
  dom.paginationInfo.textContent = `Pagina ${state.pagination.page} de ${totalPages}`;
  dom.prevPageBtn.disabled = state.pagination.page <= 1;
  dom.nextPageBtn.disabled = state.pagination.page >= totalPages;
}

function changePage(delta) {
  const totalPages = Math.max(1, Math.ceil(state.pagination.total / state.pagination.pageSize));
  const nextPage = state.pagination.page + delta;
  if (nextPage < 1 || nextPage > totalPages) return;
  state.pagination.page = nextPage;
  loadQuotes();
}

function applyFilters() {
  state.filters.search = dom.filterSearch.value.trim();
  state.filters.estado = dom.filterStatus.value;
  state.filters.clienteRut = dom.filterRut.value.trim();
  state.pagination.page = 1;
  loadQuotes();
}

function clearFilters() {
  dom.filtersForm.reset();
  state.filters = { search: "", estado: "", clienteRut: "" };
  state.pagination.page = 1;
  loadQuotes();
}

function handleTableClick(event) {
  const row = event.target.closest("tr[data-id]");
  if (!row) return;
  const quoteId = row.getAttribute("data-id");
  selectQuote(quoteId);
}

async function selectQuote(quoteId) {
  if (!quoteId) return;
  state.selectedQuoteId = quoteId;
  highlightSelectedRow();
  setDetailLoading(true);
  try {
    const detail = await getQuote(quoteId);
    state.selectedQuote = detail;
    prepareEditingItems(detail);
    renderQuoteDetail(detail);
  } catch (error) {
    console.error("Error obteniendo cotizacion", error);
    alert(error?.message || "No se pudo cargar la cotizacion.");
  } finally {
    setDetailLoading(false);
  }
}

function highlightSelectedRow() {
  if (!dom.quoteTableBody) return;
  Array.from(dom.quoteTableBody.children).forEach((row) => {
    if (row.getAttribute("data-id") === state.selectedQuoteId) {
      row.classList.add("quote-row--selected");
    } else {
      row.classList.remove("quote-row--selected");
    }
  });
}

function prepareEditingItems(detail) {
  const items = Array.isArray(detail?.items) ? detail.items : [];
  state.editingItems = items.map((item, index) => {
    const base = {
      catalogSlug: item.catalog_slug || "",
      optionValue: "",
      descripcion: item.descripcion || "",
      cantidad: Number(item.cantidad ?? 0),
      precioUF: Number(item.precio_unitario_uf ?? item.precioUF ?? 0),
      totalUF: Number(item.total_uf ?? item.totalUF ?? 0),
      nota: item.nota || "",
      orden: item.orden ?? index + 1,
    };
    const match =
      state.catalogItems.find((catalogItem) => catalogItem.categorySlug === item.catalog_slug) ||
      state.catalogItems.find(
        (catalogItem) =>
          catalogItem.label?.toLowerCase() === base.descripcion.toLowerCase() &&
          Math.abs(Number(catalogItem.valorUF) - Number(base.precioUF)) < 0.001
      );
    if (match) {
      base.catalogSlug = match.categorySlug;
      base.optionValue = match.optionValue;
      if (!base.descripcion) base.descripcion = match.label;
    }
    return base;
  });
  if (!state.editingItems.length) {
    addItem();
  } else {
    updateTotals();
  }
}

function renderQuoteDetail(detail) {
  toggleDetail(true);
  const folio = detail.quote_number || detail.quoteNumber || "";
  dom.detailTitle.textContent = folio ? `Cotizacion ${folio}` : "Cotizacion";
  dom.detailSubtitle.textContent = `Estado: ${STATUS_LABELS[detail.estado] || detail.estado}`;
  dom.quoteId.value = detail.id || "";
  dom.clientName.value = detail.cliente_nombre || "";
  dom.clientRut.value = detail.cliente_rut || "";
  dom.clientContact.value = detail.cliente_contacto || detail.contacto || "";
  dom.clientEmail.value = detail.cliente_correo || detail.correo || detail.clientEmail || "";
  dom.clientPhone.value = detail.cliente_telefono || detail.telefono || detail.clientPhone || "";
  dom.preparedBy.value = detail.prepared_by || detail.preparedBy || "";
  dom.preparedEmail.value = detail.prepared_email || detail.preparedEmail || "";
  dom.discountPercent.value = Number(detail.descuento_pct ?? detail.descuentoPct ?? 0);
  dom.ufValue.value = detail.uf_valor_clp ?? detail.ufValorClp ?? "";
  dom.validityDays.value = detail.vigencia_dias ?? detail.vigenciaDias ?? 30;
  dom.quoteNotes.value = detail.observaciones || "";
  renderItemsTable();
  updateTotals();
  renderTimeline(detail.eventos || []);
  updateActionButtons(detail.estado);
}

function renderItemsTable() {
  const rows = state.editingItems
    .map((item, index) => {
      const unit = Number(item.precioUF ?? 0);
      const total = Number(item.totalUF ?? unit * Number(item.cantidad ?? 0));
      return `
        <tr data-index="${index}">
          <td>
            <select class="item-service">
              ${buildServiceOptions(item.optionValue)}
            </select>
            <input class="item-desc" type="text" placeholder="Descripcion" value="${escapeHtml(item.descripcion || "")}">
            <textarea class="item-note" rows="2" placeholder="Nota sugerida (puedes editarla)">${escapeHtml(item.nota || "")}</textarea>
          </td>
          <td>
            <input class="item-qty" type="number" min="0" step="1" value="${Number(item.cantidad ?? 0)}">
          </td>
          <td>
            <input class="item-unit" type="number" min="0" step="0.01" value="${unit}">
          </td>
          <td class="item-total">${formatUF(total)}</td>
          <td>
            <button type="button" class="item-remove" aria-label="Eliminar servicio">&times;</button>
          </td>
        </tr>
      `;
    })
    .join("");
  dom.itemsBody.innerHTML = rows;
}

function buildServiceOptions(selectedValue) {
  if (!state.catalogItems.length) {
    const label = selectedValue ? "Servicio catalogado" : "Manual";
    return `<option value="${selectedValue || ""}">${label}</option>`;
  }
  const options = state.catalogItems
    .map((item) => {
      const value = item.optionValue;
      const isSelected = selectedValue && selectedValue === value;
      const display = `${item.label} (${formatUF(item.valorUF)} UF)`;
      return `<option value="${value}" ${isSelected ? "selected" : ""}>${display}</option>`;
    })
    .join("");
  const manualSelected = !selectedValue || !state.catalogItems.some((catalogItem) => catalogItem.optionValue === selectedValue);
  return `<option value="" ${manualSelected ? "selected" : ""}>Manual</option>${options}`;
}

function handleItemInput(event) {
  const row = event.target.closest("tr[data-index]");
  if (!row) return;
  const index = Number(row.getAttribute("data-index"));
  const item = state.editingItems[index];
  if (!item) return;
  if (event.target.classList.contains("item-desc")) {
    item.descripcion = event.target.value;
  } else if (event.target.classList.contains("item-note")) {
    item.nota = event.target.value;
  } else if (event.target.classList.contains("item-qty")) {
    item.cantidad = Math.max(0, Number(event.target.value));
  } else if (event.target.classList.contains("item-unit")) {
    item.precioUF = Math.max(0, Number(event.target.value));
  }
  item.totalUF = item.precioUF * item.cantidad;
  updateTotals();
  renderRowTotals(index);
}

function handleItemChange(event) {
  const row = event.target.closest("tr[data-index]");
  if (!row) return;
  const index = Number(row.getAttribute("data-index"));
  const item = state.editingItems[index];
  if (!item) return;
  if (event.target.classList.contains("item-service")) {
    const value = event.target.value;
    if (!value) {
      item.catalogSlug = "";
      item.optionValue = "";
      item.descripcion = "Servicio personalizado";
      item.precioUF = Number(item.precioUF ?? 0);
      item.nota = "";
    } else {
      const selected = state.catalogItems.find((catalogItem) => value === catalogItem.optionValue);
      if (selected) {
        item.catalogSlug = selected.categorySlug;
        item.optionValue = selected.optionValue;
        item.descripcion = selected.label;
        item.precioUF = Number(selected.valorUF ?? 0);
        item.nota = selected.nota || "";
      }
    }
    item.totalUF = item.precioUF * item.cantidad;
    renderRowTotals(index);
    updateTotals();
  }
}

function handleItemRemove(event) {
  if (!event.target.classList.contains("item-remove")) return;
  const row = event.target.closest("tr[data-index]");
  if (!row) return;
  if (state.editingItems.length <= 1) {
    alert("Debe existir al menos un servicio en la cotizacion.");
    return;
  }
  const index = Number(row.getAttribute("data-index"));
  state.editingItems.splice(index, 1);
  renderItemsTable();
  updateTotals();
}

function renderRowTotals(index) {
  const row = dom.itemsBody.querySelector(`tr[data-index="${index}"]`);
  if (!row) return;
  const item = state.editingItems[index];
  const totalCell = row.querySelector(".item-total");
  if (totalCell) {
    totalCell.textContent = formatUF(item.precioUF * item.cantidad);
  }
  const descInput = row.querySelector(".item-desc");
  if (descInput && descInput !== document.activeElement) {
    descInput.value = item.descripcion || "";
  }
  const noteInput = row.querySelector(".item-note");
  if (noteInput && noteInput !== document.activeElement) {
    noteInput.value = item.nota || "";
  }
  const qtyInput = row.querySelector(".item-qty");
  if (qtyInput) {
    qtyInput.value = item.cantidad;
  }
  const unitInput = row.querySelector(".item-unit");
  if (unitInput) {
    unitInput.value = item.precioUF;
  }
}

function addItem() {
  const defaultCatalog = state.catalogItems[0];
  const newItem = {
    catalogSlug: defaultCatalog ? defaultCatalog.categorySlug : "",
    optionValue: defaultCatalog ? defaultCatalog.optionValue : "",
    descripcion: defaultCatalog ? defaultCatalog.label : "Servicio personalizado",
    cantidad: 1,
    precioUF: defaultCatalog ? Number(defaultCatalog.valorUF ?? 0) : 0,
    totalUF: defaultCatalog ? Number(defaultCatalog.valorUF ?? 0) : 0,
    nota: defaultCatalog ? defaultCatalog.nota || "" : "",
    orden: state.editingItems.length + 1,
  };
  state.editingItems.push(newItem);
  renderItemsTable();
  updateTotals();
}

function updateTotals() {
  const subtotal = state.editingItems.reduce((acc, item) => acc + Number(item.precioUF || 0) * Number(item.cantidad || 0), 0);
  const discountRate = Math.min(100, Math.max(0, Number(dom.discountPercent.value || 0))) / 100;
  const discount = subtotal * discountRate;
  const net = subtotal - discount;
  const tax = net * 0.19;
  const total = net + tax;
  dom.totals.subtotal.textContent = `${formatUF(subtotal)} UF`;
  dom.totals.discount.textContent = `${formatUF(discount)} UF`;
  dom.totals.net.textContent = `${formatUF(net)} UF`;
  dom.totals.tax.textContent = `${formatUF(tax)} UF`;
  dom.totals.total.textContent = `${formatUF(total)} UF`;
}

function updateActionButtons(estado) {
  const finalStates = new Set(["aceptada", "anulada", "expirada"]);
  dom.saveBtn.disabled = finalStates.has(estado);
  dom.sendBtn.disabled = finalStates.has(estado) || estado === "enviada";
  dom.acceptBtn.disabled = estado !== "enviada";
  dom.voidBtn.disabled = finalStates.has(estado);
  dom.downloadBtn.disabled = !state.selectedQuoteId;
}

function togglePane(paneName) {
  if (!paneName) return;
  const pane = document.querySelector(`[data-pane="${paneName}"]`);
  const toggle = document.querySelector(`[data-toggle-pane="${paneName}"]`);
  if (!pane || !toggle) return;
  const isCollapsed = pane.getAttribute("data-collapsed") === "true";
  const nextCollapsed = !isCollapsed;
  pane.setAttribute("data-collapsed", String(nextCollapsed));
  refreshPaneToggle(paneName);
}

function refreshPaneToggle(paneName) {
  if (!paneName) return;
  const pane = document.querySelector(`[data-pane="${paneName}"]`);
  const toggle = document.querySelector(`[data-toggle-pane="${paneName}"]`);
  if (!pane || !toggle) return;
  const collapsed = pane.getAttribute("data-collapsed") === "true";
  toggle.textContent = collapsed ? "Expandir" : "Contraer";
  toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
}

function ensurePaneExpanded(paneName) {
  if (!paneName) return;
  const pane = document.querySelector(`[data-pane="${paneName}"]`);
  if (!pane) return;
  if (pane.getAttribute("data-collapsed") === "true") {
    pane.setAttribute("data-collapsed", "false");
  }
  refreshPaneToggle(paneName);
}

function toggleDetail(show) {
  if (show) {
    ensurePaneExpanded("detail");
    dom.detailPlaceholder.setAttribute("hidden", "hidden");
    dom.detailContainer.removeAttribute("hidden");
  } else {
    dom.detailContainer.setAttribute("hidden", "hidden");
    dom.detailPlaceholder.removeAttribute("hidden");
    dom.detailTitle.textContent = "Detalle";
    dom.detailSubtitle.textContent = "Selecciona una cotizacion o crea una nueva.";
  }
}

function setListLoading(isLoading) {
  state.loadingList = isLoading;
  dom.newQuoteBtn.disabled = isLoading;
  dom.applyFiltersBtn.disabled = isLoading;
  dom.clearFiltersBtn.disabled = isLoading;
  dom.prevPageBtn.disabled = isLoading || dom.prevPageBtn.disabled;
  dom.nextPageBtn.disabled = isLoading || dom.nextPageBtn.disabled;
}

function setDetailLoading(isLoading) {
  state.loadingDetail = isLoading;
  dom.detailForm.querySelectorAll("input, textarea, select, button").forEach((el) => {
    if (el.id === "download-quote-btn") return;
    el.disabled = isLoading;
  });
}

async function saveQuote() {
  if (!validateForm()) {
    return;
  }
  const payload = collectPayload();
  setDetailLoading(true);
  try {
    let response;
    if (state.selectedQuoteId) {
      response = await updateQuote(state.selectedQuoteId, payload);
    } else {
      response = await createQuote(payload);
      state.selectedQuoteId = response?.id;
    }
    await loadQuotes();
    if (state.selectedQuoteId) {
      await selectQuote(state.selectedQuoteId);
    }
    alert("Cotizacion guardada correctamente.");
  } catch (error) {
    console.error("Error guardando cotizacion", error);
    alert(error?.message || "No se pudo guardar la cotizacion.");
  } finally {
    setDetailLoading(false);
  }
}

function validateForm() {
  if (!dom.clientName.value.trim()) {
    alert("Falta el nombre del cliente.");
    return false;
  }
  if (!dom.clientRut.value.trim()) {
    alert("Falta el RUT del cliente.");
    return false;
  }
  const email = dom.clientEmail.value.trim();
  if (!email) {
    alert("Falta el correo del cliente.");
    return false;
  }
  if (!isValidEmail(email)) {
    alert("El correo del cliente no es valido.");
    return false;
  }
  if (!state.editingItems.length) {
    alert("Debes agregar al menos un servicio.");
    return false;
  }
  const invalidItem = state.editingItems.some(
    (item) => Number(item.cantidad) < 0 || Number(item.precioUF) < 0
  );
  if (invalidItem) {
    alert("Los servicios deben tener cantidad y precio en UF validos.");
    return false;
  }
  return true;
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function collectPayload() {
  const cliente = {
    nombre: dom.clientName.value.trim(),
    rut: dom.clientRut.value.trim(),
    contacto: dom.clientContact.value.trim(),
    correo: dom.clientEmail.value.trim(),
    telefono: dom.clientPhone.value.trim(),
  };
  const items = state.editingItems;
  const preparedByRaw = dom.preparedBy.value.trim() || cliente.contacto || cliente.nombre || "Administracion";
  return {
    cliente,
    items: items.map((item, index) => ({
      descripcion: item.descripcion || "Servicio",
      cantidad: Number(item.cantidad || 0),
      precio_uf: Number(item.precioUF || 0),
      nota: item.nota || "",
      orden: index + 1,
      catalog_slug: item.catalogSlug || null,
    })),
    prepared_by: preparedByRaw,
    prepared_email: dom.preparedEmail.value.trim() || null,
    descuento_pct: Number(dom.discountPercent.value || 0),
    uf_valor_clp: dom.ufValue.value ? Number(dom.ufValue.value) : null,
    vigencia_dias: Number(dom.validityDays.value || 30),
    observaciones: dom.quoteNotes.value.trim() || null,
  };
}

async function updateStatus(targetStatus) {
  if (!state.selectedQuoteId) {
    alert("Selecciona una cotizacion primero.");
    return;
  }
  const mensajes = {
    enviada: "Enviar la cotizacion y marcar como enviada?",
    aceptada: "Marcar como aceptada?",
    anulada: "Anular la cotizacion?",
  };
  const confirmMessage = mensajes[targetStatus] || "Confirmas la accion?";
  if (!confirm(confirmMessage)) return;
  setDetailLoading(true);
  try {
    await changeQuoteStatus(state.selectedQuoteId, { estado: targetStatus });
    await loadQuotes();
    await selectQuote(state.selectedQuoteId);
    alert("Estado actualizado.");
  } catch (error) {
    console.error("Error cambiando estado", error);
    alert(error?.message || "No se pudo cambiar el estado.");
  } finally {
    setDetailLoading(false);
  }
}

async function downloadCurrentQuote() {
  if (!state.selectedQuote || !state.selectedQuoteId) {
    alert("Selecciona una cotizacion para descargar.");
    return;
  }
  try {
    const data = buildPdfPayload();
    await downloadQuotePdf(data);
    await logQuotePdfDownload(state.selectedQuoteId);
  } catch (error) {
    console.error("Error generando PDF", error);
    alert(error?.message || "No se pudo generar el PDF.");
  }
}

function buildPdfPayload() {
  const totals = computeTotals();
  const cliente = {
    nombre: dom.clientName.value.trim(),
    rut: dom.clientRut.value.trim(),
    contacto: dom.clientContact.value.trim(),
    correo: dom.clientEmail.value.trim(),
    telefono: dom.clientPhone.value.trim(),
  };
  const info = {
    fecha: formatDateTime(state.selectedQuote?.created_at || new Date().toISOString()),
    estado: state.selectedQuote?.estado || "borrador",
    vigencia: state.selectedQuote?.vigencia_hasta ? formatDateTime(state.selectedQuote.vigencia_hasta) : "",
    observaciones: dom.quoteNotes.value.trim(),
  };
  const items = state.editingItems.map((item) => ({
    descripcion: item.descripcion || "Servicio",
    cantidad: Number(item.cantidad || 0),
    precioUF: Number(item.precioUF || 0),
    totalUF: Number(item.precioUF || 0) * Number(item.cantidad || 0),
    nota: item.nota || "",
  }));
  return {
    folio: state.selectedQuote?.quote_number || "",
    cliente,
    info,
    items,
    totals,
  };
}

function computeTotals() {
  const subtotal = state.editingItems.reduce(
    (acc, item) => acc + Number(item.precioUF || 0) * Number(item.cantidad || 0),
    0
  );
  const discountRate = Math.min(100, Math.max(0, Number(dom.discountPercent.value || 0))) / 100;
  const discount = subtotal * discountRate;
  const net = subtotal - discount;
  const tax = net * 0.19;
  const total = net + tax;
  return {
    subtotalUF: subtotal,
    descuentoUF: discount,
    netoUF: net,
    taxUF: tax,
    totalUF: total,
  };
}

function startNewQuote() {
  state.selectedQuoteId = null;
  state.selectedQuote = null;
  state.editingItems = [];
  addItem();
  dom.detailTitle.textContent = "Nueva cotizacion";
  dom.detailSubtitle.textContent = "Completa los datos y guarda para generar el folio.";
  dom.detailForm.reset();
  dom.quoteId.value = "";
  toggleDetail(true);
  updateActionButtons("borrador");
  updateTotals();
}

async function searchClient() {
  const value = dom.clientRut.value.trim() || dom.clientName.value.trim();
  if (!value) {
    alert("Ingresa el RUT o nombre antes de buscar.");
    return;
  }
  try {
    const clients = await listClients({ query: value, limit: 5 });
    if (!clients.length) {
      alert("No se encontraron clientes con ese criterio.");
      return;
    }
    const normalizedRut = dom.clientRut.value.trim().replace(/\./g, "").toLowerCase();
    const exact = clients.find((client) => (client.rut || "").replace(/\./g, "").toLowerCase() === normalizedRut);
    const match = exact || clients[0];
    dom.clientName.value = match.nombre || "";
    dom.clientRut.value = match.rut || "";
    dom.clientContact.value = match.contacto || "";
    dom.clientEmail.value = match.correo || "";
    dom.clientPhone.value = match.telefono || "";
  } catch (error) {
    console.error("Error buscando cliente", error);
    alert(error?.message || "No se pudo buscar el cliente.");
  }
}

async function saveClientFromForm() {
  const nombre = dom.clientName.value.trim();
  const rut = dom.clientRut.value.trim();
  if (!nombre || !rut) {
    alert("Ingresa al menos nombre y RUT para guardar el cliente.");
    return;
  }
  const payload = {
    nombre,
    rut,
    contacto: dom.clientContact.value.trim() || null,
    correo: dom.clientEmail.value.trim() || null,
    telefono: dom.clientPhone.value.trim() || null,
  };
  dom.clientSaveBtn.disabled = true;
  try {
    const saved = await createClient(payload);
    if (saved) {
      dom.clientName.value = saved.nombre || nombre;
      dom.clientRut.value = saved.rut || rut;
      dom.clientContact.value = saved.contacto || "";
      dom.clientEmail.value = saved.correo || "";
      dom.clientPhone.value = saved.telefono || "";
    }
    alert("Cliente guardado correctamente.");
  } catch (error) {
    console.error("Error guardando cliente", error);
    alert(error?.message || "No se pudo guardar el cliente.");
  } finally {
    dom.clientSaveBtn.disabled = false;
  }
}

function renderTimeline(events) {
  if (!dom.timeline) return;
  if (!events.length) {
    dom.timeline.innerHTML = `<div class="empty-state">Sin eventos registrados.</div>`;
    return;
  }
  const items = events
    .map((event) => {
      const fecha = formatDateTime(event.created_at);
      const detalle = event.descripcion || event.tipo;
      const actor = event.actor_email ? `Por ${event.actor_email}` : "";
      return `
        <div class="timeline-item">
          <div class="meta">
            <span>${fecha}</span>
            <span>${event.tipo}</span>
          </div>
          <div>${detalle}</div>
          ${actor ? `<div class="meta">${actor}</div>` : ""}
        </div>
      `;
    })
    .join("");
  dom.timeline.innerHTML = items;
}

function formatDateTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("es-CL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatUF(amount) {
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(amount || 0));
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
