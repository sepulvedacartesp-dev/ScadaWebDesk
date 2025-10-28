const QUOTE_MODEL = {
  // Update these values to adjust pricing or add new catalog entries.
  taxRate: 0.19,
  catalog: {
    containers: {
      firstUnitUF: 3.16,
      additionalUnitUF: 0.76,
      primaryLabel: "Contenedor principal",
      additionalLabel: "Contenedores adicionales",
      note: "Incluye habilitacion y despliegue inicial.",
    },
    nexbox: {
      unitUF: 1,
      label: "NexBox (8 canales)",
      note: "Modulo de expansion inalambico de 8 canales.",
    },
    internet: {
      unitUF: 1.5,
      label: "Suministro de internet en sitio",
      note: "Incluye gestion y soporte basico del enlace.",
    },
    support: {
      options: {
        basic: {
          planId: "basic",
          label: "Soporte basico",
          description: "Sin costo adicional. 1 requerimiento o llamada al mes.",
          unitUF: 0,
        },
        plus: {
          planId: "plus",
          label: "Soporte Plus",
          description: "Hasta 4 requerimientos o llamadas al mes.",
          unitUF: 2,
        },
      },
      defaultPlan: "basic",
    },
  },
};

const form = document.getElementById("quote-form");
const companyNameInput = document.getElementById("company-name");
const companyRutInput = document.getElementById("company-rut");
const contactNameInput = document.getElementById("contact-name");
const containersInput = document.getElementById("containers-count");
const nexboxInput = document.getElementById("nexbox-count");
const internetInput = document.getElementById("internet-service");
const supportSelect = document.getElementById("support-level");
const discountInput = document.getElementById("discount-rate");

const summaryCompany = document.getElementById("summary-company");
const summaryRut = document.getElementById("summary-rut");
const summaryContact = document.getElementById("summary-contact");

const summaryBody = document.getElementById("summary-body");
const summaryEmpty = document.getElementById("summary-empty");
const subtotalNode = document.getElementById("subtotal-uf");
const discountNode = document.getElementById("discount-uf");
const netNode = document.getElementById("net-uf");
const taxNode = document.getElementById("tax-uf");
const totalNode = document.getElementById("grand-total-uf");
const downloadBtn = document.getElementById("download-pdf");

const ufFormatter = new Intl.NumberFormat("es-CL", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat("es-CL", {
  style: "percent",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function parseInteger(value) {
  if (value === "" || value === null || value === undefined) {
    return 0;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.max(0, Math.floor(parsed));
}

function parseFloatSafe(value) {
  if (value === "" || value === null || value === undefined) {
    return 0;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return parsed;
}

function formatUF(amount) {
  return ufFormatter.format(amount);
}

function formatPercent(rate) {
  return percentFormatter.format(rate);
}

function sanitizeFileName(name) {
  return String(name || "cliente")
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, "_")
    .slice(0, 60) || "cliente";
}

function collectFormData() {
  return {
    companyName: companyNameInput.value.trim(),
    companyRut: companyRutInput.value.trim(),
    contactName: contactNameInput.value.trim(),
    containers: parseInteger(containersInput.value),
    nexbox: parseInteger(nexboxInput.value),
    internet: Boolean(internetInput.checked),
    support: supportSelect.value || QUOTE_MODEL.catalog.support.defaultPlan,
    discountPercent: clamp(parseFloatSafe(discountInput.value), 0, 100),
  };
}

function buildLineItems(data) {
  const items = [];
  const containers = QUOTE_MODEL.catalog.containers;
  if (data.containers > 0) {
    items.push({
      id: "containers-primary",
      label: containers.primaryLabel,
      quantity: 1,
      unitPriceUF: containers.firstUnitUF,
      totalUF: containers.firstUnitUF,
      note: containers.note,
    });
    const extras = Math.max(data.containers - 1, 0);
    if (extras > 0) {
      items.push({
        id: "containers-extra",
        label: `${containers.additionalLabel} (${extras})`,
        quantity: extras,
        unitPriceUF: containers.additionalUnitUF,
        totalUF: extras * containers.additionalUnitUF,
        note: "Valores por contenedor adicional.",
      });
    }
  }

  if (data.nexbox > 0) {
    const nexbox = QUOTE_MODEL.catalog.nexbox;
    items.push({
      id: "nexbox",
      label: `${nexbox.label}`,
      quantity: data.nexbox,
      unitPriceUF: nexbox.unitUF,
      totalUF: data.nexbox * nexbox.unitUF,
      note: nexbox.note,
    });
  }

  if (data.internet) {
    const internet = QUOTE_MODEL.catalog.internet;
    items.push({
      id: "internet",
      label: internet.label,
      quantity: 1,
      unitPriceUF: internet.unitUF,
      totalUF: internet.unitUF,
      note: internet.note,
    });
  }

  const supportCatalog = QUOTE_MODEL.catalog.support;
  const selectedPlan = supportCatalog.options[data.support] || supportCatalog.options[supportCatalog.defaultPlan];
  items.push({
    id: `support-${selectedPlan.planId}`,
    label: selectedPlan.label,
    quantity: 1,
    unitPriceUF: selectedPlan.unitUF,
    totalUF: selectedPlan.unitUF,
    note: selectedPlan.description,
  });

  return items;
}

function computeQuote(data) {
  const lineItems = buildLineItems(data);
  const subtotalUF = lineItems.reduce((acc, item) => acc + item.totalUF, 0);
  const discountRate = data.discountPercent / 100;
  const discountUF = subtotalUF * discountRate;
  const netUF = subtotalUF - discountUF;
  const taxUF = netUF * QUOTE_MODEL.taxRate;
  const totalUF = netUF + taxUF;

  return {
    lineItems,
    subtotalUF,
    discountRate,
    discountUF,
    netUF,
    taxUF,
    totalUF,
  };
}

function updateClientSummary(data) {
  summaryCompany.textContent = data.companyName || "--";
  summaryRut.textContent = data.companyRut || "--";
  summaryContact.textContent = data.contactName || "--";
}

function renderLineItems(lineItems) {
  summaryBody.textContent = "";
  const fragment = document.createDocumentFragment();
  lineItems.forEach((item) => {
    const row = document.createElement("tr");

    const serviceCell = document.createElement("td");
    const labelWrapper = document.createElement("span");
    labelWrapper.className = "summary-label";

    const titleSpan = document.createElement("span");
    titleSpan.textContent = item.label;
    labelWrapper.appendChild(titleSpan);

    if (item.note) {
      const noteSpan = document.createElement("small");
      noteSpan.textContent = item.note;
      labelWrapper.appendChild(noteSpan);
    }

    serviceCell.appendChild(labelWrapper);
    row.appendChild(serviceCell);

    const quantityCell = document.createElement("td");
    quantityCell.textContent = item.quantity.toString();
    row.appendChild(quantityCell);

    const unitCell = document.createElement("td");
    unitCell.textContent = formatUF(item.unitPriceUF);
    row.appendChild(unitCell);

    const totalCell = document.createElement("td");
    totalCell.textContent = formatUF(item.totalUF);
    row.appendChild(totalCell);

    fragment.appendChild(row);
  });
  summaryBody.appendChild(fragment);
}

function renderTotals(quote) {
  subtotalNode.textContent = `${formatUF(quote.subtotalUF)} UF`;
  discountNode.textContent = `${formatUF(quote.discountUF)} UF`;
  netNode.textContent = `${formatUF(quote.netUF)} UF`;
  taxNode.textContent = `${formatUF(quote.taxUF)} UF`;
  totalNode.textContent = `${formatUF(quote.totalUF)} UF`;

  const hasCharges = quote.subtotalUF > 0;
  summaryEmpty.hidden = hasCharges;
}

function updateDownloadState(isReady) {
  if (!downloadBtn) {
    return;
  }
  downloadBtn.disabled = !isReady;
}

function updateQuote() {
  if (!form) {
    return;
  }
  const data = collectFormData();
  const quote = computeQuote(data);

  updateClientSummary(data);
  renderLineItems(quote.lineItems);
  renderTotals(quote);

  const formReady = form.checkValidity();
  updateDownloadState(formReady);

  if (downloadBtn) {
    downloadBtn.dataset.discountRate = quote.discountRate.toString();
    downloadBtn.dataset.subtotalUf = quote.subtotalUF.toString();
    downloadBtn.dataset.netUf = quote.netUF.toString();
    downloadBtn.dataset.taxUf = quote.taxUF.toString();
    downloadBtn.dataset.totalUf = quote.totalUF.toString();
  }
}

function splitNoteLines(doc, text, maxWidth) {
  return doc.splitTextToSize(text, maxWidth);
}

function generatePdf(data, quote) {
  const jspdfNamespace = window.jspdf;
  if (!jspdfNamespace || !jspdfNamespace.jsPDF) {
    console.error("jsPDF no disponible");
    return;
  }
  const doc = new jspdfNamespace.jsPDF({
    orientation: "portrait",
    unit: "pt",
    format: "a4",
  });

  const marginX = 40;
  const contentWidth = 460;
  let cursorY = 60;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.text("Propuesta comercial SurNex", marginX, cursorY);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  cursorY += 18;
  doc.text(`Fecha: ${new Date().toLocaleDateString("es-CL")}`, marginX, cursorY);
  cursorY += 14;
  doc.text(`Cliente: ${data.companyName || "-"}`, marginX, cursorY);
  cursorY += 14;
  doc.text(`RUT: ${data.companyRut || "-"}`, marginX, cursorY);
  cursorY += 14;
  doc.text(`Contacto: ${data.contactName || "-"}`, marginX, cursorY);
  cursorY += 22;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(13);
  doc.text("Detalle de servicios", marginX, cursorY);
  cursorY += 16;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Servicio", marginX, cursorY);
  doc.text("Cantidad", marginX + 250, cursorY);
  doc.text("UF c/u", marginX + 330, cursorY);
  doc.text("Total UF", marginX + 420, cursorY);
  cursorY += 8;
  doc.setLineWidth(0.5);
  doc.line(marginX, cursorY, marginX + contentWidth, cursorY);
  cursorY += 14;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  quote.lineItems.forEach((item) => {
    if (cursorY > 720) {
      doc.addPage();
      cursorY = 60;
    }
    doc.text(item.label, marginX, cursorY);
    doc.text(item.quantity.toString(), marginX + 250, cursorY);
    doc.text(formatUF(item.unitPriceUF), marginX + 330, cursorY, { align: "right" });
    doc.text(formatUF(item.totalUF), marginX + 420, cursorY, { align: "right" });
    cursorY += 14;
    if (item.note) {
      const noteLines = splitNoteLines(doc, item.note, contentWidth - 20);
      doc.setFontSize(10);
      noteLines.forEach((line) => {
        if (cursorY > 720) {
          doc.addPage();
          cursorY = 60;
        }
        doc.text(line, marginX + 12, cursorY);
        cursorY += 12;
      });
      doc.setFontSize(11);
    }
    cursorY += 4;
  });

  cursorY += 6;
  doc.setLineWidth(0.5);
  doc.line(marginX, cursorY, marginX + contentWidth, cursorY);
  cursorY += 16;

  const totalsXLabel = marginX + 240;
  const totalsXValue = marginX + contentWidth;

  doc.setFont("helvetica", "bold");
  doc.text("Subtotal:", totalsXLabel, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(quote.subtotalUF)} UF`, totalsXValue, cursorY, { align: "right" });
  cursorY += 14;

  doc.setFont("helvetica", "bold");
  doc.text(`Descuento (${formatPercent(quote.discountRate)}):`, totalsXLabel, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(quote.discountUF)} UF`, totalsXValue, cursorY, { align: "right" });
  cursorY += 14;

  doc.setFont("helvetica", "bold");
  doc.text("Total neto:", totalsXLabel, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(quote.netUF)} UF`, totalsXValue, cursorY, { align: "right" });
  cursorY += 14;

  doc.setFont("helvetica", "bold");
  doc.text(`IVA (${formatPercent(QUOTE_MODEL.taxRate)}):`, totalsXLabel, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(quote.taxUF)} UF`, totalsXValue, cursorY, { align: "right" });
  cursorY += 14;

  doc.setFont("helvetica", "bold");
  doc.text("Total con IVA:", totalsXLabel, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(quote.totalUF)} UF`, totalsXValue, cursorY, { align: "right" });
  cursorY += 24;

  doc.setFont("helvetica", "italic");
  doc.setFontSize(10);
  doc.text(
    "Los precios estan expresados en UF. Ajusta QUOTE_MODEL en cotizador.js para actualizar montos o agregar servicios.",
    marginX,
    cursorY
  );

  const fileName = `Cotizacion_${sanitizeFileName(data.companyName || "cliente")}.pdf`;
  doc.save(fileName);
}

function handleDownload() {
  if (!form || !form.checkValidity()) {
    form?.reportValidity();
    return;
  }
  const data = collectFormData();
  const quote = computeQuote(data);
  generatePdf(data, quote);
}

function bindInputs() {
  const fields = [
    companyNameInput,
    companyRutInput,
    contactNameInput,
    containersInput,
    nexboxInput,
    supportSelect,
    discountInput,
  ];
  fields.forEach((field) => {
    field?.addEventListener("input", updateQuote);
  });
  internetInput?.addEventListener("change", updateQuote);
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    updateQuote();
  });
  downloadBtn?.addEventListener("click", handleDownload);
}

bindInputs();
updateQuote();
