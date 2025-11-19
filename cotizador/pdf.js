function ensureJsPdf() {
  const jsPdfNamespace = window.jspdf;
  if (!jsPdfNamespace || typeof jsPdfNamespace.jsPDF !== "function") {
    throw new Error("No se encontro jsPDF. Verifica que la libreria este cargada.");
  }
  return jsPdfNamespace.jsPDF;
}

const COMPANY_PAYMENT_INFO = {
  nombre: "SurNex Control y Desarrollo Tecnológico SpA",
  rut: "78.299.434-4",
  banco: "Banco Santander",
  cuentaCorriente: "0000000000",
  modo: "Transferencia electrónica",
  correoPagos: "pagos@surnex.cl",
};

function formatUF(value) {
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function sanitizeFileName(name) {
  return String(name || "cotizacion")
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, "_")
    .slice(0, 80) || "cotizacion";
}

function wrapText(doc, text, maxWidth) {
  const words = String(text || "").split(/\s+/);
  const lines = [];
  let currentLine = "";
  words.forEach((word) => {
    const testLine = currentLine ? `${currentLine} ${word}` : word;
    const testWidth = doc.getTextWidth(testLine);
    if (testWidth > maxWidth && currentLine) {
      lines.push(currentLine);
      currentLine = word;
    } else {
      currentLine = testLine;
    }
  });
  if (currentLine) {
    lines.push(currentLine);
  }
  return lines;
}

function loadImageElement(src) {
  return new Promise((resolve) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = encodeURI(src);
  });
}

async function loadLogoImage() {
  const logoCandidates = [
   // "/Imagenes/Logo_Surnex.png",
    "/Imagenes/Surnex Logo.png",
   // "/Imagenes/Surnex Logo y Slogan.png",
   // "/imagen/surnex_logo.png",
    //"Imagenes/Logo_Surnex.png",
    //"Imagenes/Surnex Logo.png",
  ];
  for (const src of logoCandidates) {
    const image = await loadImageElement(src);
    if (image) {
      return { image, src };
    }
  }
  return null;
}

export async function downloadQuotePdf(payload) {
  const jsPDF = ensureJsPdf();
  const data = payload || {};
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const marginX = 50;
  let cursorY = 60;
  const pageHeight = doc.internal.pageSize.getHeight();
  const contentWidth = doc.internal.pageSize.getWidth() - marginX * 2;
  const logoResult = await loadLogoImage();

  if (logoResult?.image) {
    const LOGO_WIDTH_OVERRIDE = 100; // 120 Ajusta este valor para forzar ancho fijo del logo.
    const LOGO_SCALE = 0.35; // Escala global del logo (0.5 = 50% mas pequeno).
    const maxLogoWidth = 100;
    const naturalWidth = logoResult.image.naturalWidth || maxLogoWidth;
    const naturalHeight = logoResult.image.naturalHeight || maxLogoWidth * 0.5;
    const computedWidth = Math.min(maxLogoWidth, naturalWidth);
    const baseWidth = LOGO_WIDTH_OVERRIDE || computedWidth;
    const logoWidth = baseWidth * LOGO_SCALE;
    const aspectRatio = naturalHeight && naturalWidth ? naturalHeight / naturalWidth : 1;
    const logoHeight = logoWidth * aspectRatio;
    const pageWidth = doc.internal.pageSize.getWidth();
    const logoX = pageWidth - marginX - logoWidth;
    const logoY = 26;
    try {
      doc.addImage(logoResult.image, "PNG", logoX, logoY, logoWidth, logoHeight);
      cursorY = Math.max(cursorY, logoY + logoHeight + 22);
    } catch (error) {
      console.warn("No se pudo insertar el logo en el PDF", error);
    }
  } else {
    console.warn("No se encontro el logo en Imagenes/Logo_Surnex.png ni en rutas de respaldo.");
  }

  const cliente = data.cliente || {};
  const info = data.info || {};
  const totals = data.totals || {};
  const items = Array.isArray(data.items) ? data.items : [];

  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.text("Cotizacion comercial", marginX, cursorY);
  cursorY += 24;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  doc.text(`Folio: ${data.folio || "--"}`, marginX, cursorY);
  cursorY += 16;
  doc.text(`Fecha: ${info.fecha || "--"}`, marginX, cursorY);
  cursorY += 16;
  doc.text(`Estado: ${String(info.estado || "--").toUpperCase()}`, marginX, cursorY);
  cursorY += 24;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.text("Cliente", marginX, cursorY);
  cursorY += 18;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  const clientLines = [
    `Nombre: ${cliente.nombre || "--"}`,
    `RUT: ${cliente.rut || "--"}`,
    `Contacto: ${cliente.contacto || "--"}`,
    `Correo: ${cliente.correo || "--"}`,
    `Telefono: ${cliente.telefono || "--"}`,
  ];
  clientLines.forEach((line) => {
    doc.text(line, marginX, cursorY);
    cursorY += 14;
  });
  cursorY += 10;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.text("Detalle de servicios", marginX, cursorY);
  cursorY += 18;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Servicio", marginX, cursorY);
  doc.text("Cantidad", marginX + 220, cursorY);
  doc.text("UF c/u", marginX + 300, cursorY);
  doc.text("Total UF", marginX + 380, cursorY);
  cursorY += 10;
  doc.line(marginX, cursorY, marginX + contentWidth, cursorY);
  cursorY += 12;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  items.forEach((item) => {
    if (cursorY > pageHeight - 80) {
      doc.addPage();
      cursorY = 60;
    }
    doc.text(item.descripcion || "--", marginX, cursorY);
    doc.text(String(item.cantidad ?? "--"), marginX + 220, cursorY);
    doc.text(formatUF(item.precioUF ?? 0), marginX + 300, cursorY, { align: "right" });
    doc.text(formatUF(item.totalUF ?? 0), marginX + 380, cursorY, { align: "right" });
    cursorY += 12;
    if (item.nota) {
      const noteLines = wrapText(doc, item.nota, contentWidth - 40);
      noteLines.forEach((line) => {
        if (cursorY > pageHeight - 80) {
          doc.addPage();
          cursorY = 60;
        }
        doc.text(`- ${line}`, marginX + 12, cursorY);
        cursorY += 12;
      });
    }
    cursorY += 6;
  });

  cursorY += 4;
  doc.line(marginX, cursorY, marginX + contentWidth, cursorY);
  cursorY += 18;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Subtotal", marginX + 250, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(totals.subtotalUF)} UF`, marginX + contentWidth, cursorY, { align: "right" });
  cursorY += 14;

  doc.setFont("helvetica", "bold");
  doc.text("Descuento", marginX + 250, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(totals.descuentoUF)} UF`, marginX + contentWidth, cursorY, { align: "right" });
  cursorY += 14;

  doc.setFont("helvetica", "bold");
  doc.text("Total neto", marginX + 250, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(totals.netoUF)} UF`, marginX + contentWidth, cursorY, { align: "right" });
  cursorY += 14;

  doc.setFont("helvetica", "bold");
  doc.text("IVA (19%)", marginX + 250, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(totals.taxUF)} UF`, marginX + contentWidth, cursorY, { align: "right" });
  cursorY += 14;

  doc.setFont("helvetica", "bold");
  doc.text("Total + IVA", marginX + 250, cursorY);
  doc.setFont("helvetica", "normal");
  doc.text(`${formatUF(totals.totalUF)} UF`, marginX + contentWidth, cursorY, { align: "right" });
  cursorY += 24;

  if (info.vigencia) {
    doc.setFont("helvetica", "italic");
    doc.setFontSize(10);
    doc.text(`Cotizacion valida hasta: ${info.vigencia}`, marginX, cursorY);
    cursorY += 12;
  }
  if (info.observaciones) {
    doc.setFont("helvetica", "normal");
    const obsLines = wrapText(doc, `Observaciones: ${info.observaciones}`, contentWidth);
    obsLines.forEach((line) => {
      if (cursorY > pageHeight - 60) {
        doc.addPage();
        cursorY = 60;
      }
      doc.text(line, marginX, cursorY);
      cursorY += 12;
    });
  }

  cursorY = renderCompanyPaymentInfo(doc, cursorY + 16, marginX, contentWidth, pageHeight);

  const fileNameParts = [
    "Cotizacion",
    data.folio || "",
    sanitizeFileName(cliente.nombre || ""),
  ].filter(Boolean);
  const fileName = fileNameParts.join("_") || "Cotizacion";
  doc.save(`${fileName}.pdf`);
}

function renderCompanyPaymentInfo(doc, startY, marginX, contentWidth, pageHeight) {
  let cursorY = startY;
  if (cursorY > pageHeight - 80) {
    doc.addPage();
    cursorY = 60;
  }
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.text("Datos para pago", marginX, cursorY);
  cursorY += 16;
  const infoLines = [
    `Nombre: ${COMPANY_PAYMENT_INFO.nombre}`,
    `RUT: ${COMPANY_PAYMENT_INFO.rut}`,
    `Banco: ${COMPANY_PAYMENT_INFO.banco}`,
    `Cuenta corriente: ${COMPANY_PAYMENT_INFO.cuentaCorriente}`,
    `metodo de pago: ${COMPANY_PAYMENT_INFO.modo}`,
    `Correo electrónico pagos: ${COMPANY_PAYMENT_INFO.correoPagos}`,
  ];
  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  infoLines.forEach((line) => {
    if (cursorY > pageHeight - 60) {
      doc.addPage();
      cursorY = 60;
      doc.setFont("helvetica", "bold");
      doc.setFontSize(12);
      doc.text("Datos para pago (cont.)", marginX, cursorY);
      cursorY += 16;
      doc.setFont("helvetica", "normal");
      doc.setFontSize(11);
    }
    doc.text(line, marginX, cursorY, { maxWidth: contentWidth });
    cursorY += 14;
  });
  return cursorY;
}
