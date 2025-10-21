const BACKEND_HTTP = "https://scadawebdesk.onrender.com";

const API_BASE = `${BACKEND_HTTP}/api/tendencias`;

const TAGS_ENDPOINT = `${API_BASE}/tags`;



const statusLabel = document.getElementById("status");

const openLoginBtn = document.getElementById("open-login");

const closeLoginBtn = document.getElementById("close-login");

const logoutBtn = document.getElementById("logout-btn");

const loginDialog = document.getElementById("login-dialog");

const loginForm = document.getElementById("login-form");

const emailInput = document.getElementById("email");

const passwordInput = document.getElementById("password");



const apiStatusChip = document.getElementById("api-status");

const currentUserLabel = document.getElementById("current-user");

const currentCompanyLabel = document.getElementById("current-company");



const brandGroup = document.getElementById("brand-group");

const brandLogoImg = document.getElementById("company-logo");

const brandLogoFallback = document.querySelector(".brand-logo");

const mainTitleNode = document.getElementById("main-title");



const trendForm = document.getElementById("trend-form");

const tagSelect = document.getElementById("trend-tag");

const rangeSelect = document.getElementById("trend-range");

const customRange = document.getElementById("custom-range");

const fromInput = document.getElementById("trend-from");

const toInput = document.getElementById("trend-to");

const resolutionSelect = document.getElementById("trend-resolution");

const runButton = document.getElementById("run-query");



const metricGrid = document.getElementById("metric-grid");

const metricPlaceholder = document.getElementById("metric-placeholder");



const downloadCsvBtn = document.getElementById("download-csv");

const trendCanvas = document.getElementById("trend-canvas");

const trendFeedback = document.getElementById("trend-feedback");



const DEFAULT_MAIN_TITLE = "SurNex SCADA";



let chartInstance = null;

let lastSeriesCollection = [];



const state = {

  user: null,

  token: null,

  empresaId: null,

};



function setStatus(message) {

  if (statusLabel) {

    statusLabel.textContent = message;

  }

}



function setApiStatus(message, connected) {

  if (!apiStatusChip) return;

  apiStatusChip.textContent = message;

  apiStatusChip.classList.toggle("chip-connected", !!connected);

  apiStatusChip.classList.toggle("chip-disconnected", !connected);

}



function showFeedback(message, tone = "info") {

  if (!trendFeedback) return;

  trendFeedback.textContent = message || "";

  trendFeedback.dataset.tone = tone;

}



function computeInitials(title) {

  if (!title) return "SW";

  const parts = String(title).trim().split(/\s+/).filter(Boolean);

  if (!parts.length) return "SW";

  return parts

    .slice(0, 2)

    .map((word) => (word && word[0] ? word[0].toUpperCase() : ""))

    .join("") || "SW";

}



function hydrateMainTitle() {

  const stored = sessionStorage.getItem("scada-main-title") || localStorage.getItem("scada-main-title");

  const domTitle = mainTitleNode?.textContent?.trim();

  const resolved = (stored && stored.trim()) || domTitle || DEFAULT_MAIN_TITLE;

  if (mainTitleNode) {

    mainTitleNode.textContent = resolved;

  }

  document.title = resolved;

  sessionStorage.setItem("scada-main-title", resolved);

  return resolved;

}



function updateBrandLogo(empresaId, title) {

  if (!brandGroup || !brandLogoImg || !brandLogoFallback) return;

  const resolvedTitle = title || mainTitleNode?.textContent || DEFAULT_MAIN_TITLE;

  const initials = computeInitials(resolvedTitle);



  brandLogoFallback.textContent = initials;

  brandLogoFallback.hidden = false;



  if (!empresaId) {

    brandLogoImg.hidden = true;

    brandLogoImg.removeAttribute("src");

    brandGroup.classList.remove("brand-group--with-logo");

    return;

  }



  const logoUrl = `${BACKEND_HTTP}/logos/${encodeURIComponent(empresaId)}.jpg?v=${Date.now()}`;

  brandLogoImg.onload = () => {

    brandLogoFallback.hidden = true;

    brandLogoImg.hidden = false;

    brandGroup.classList.add("brand-group--with-logo");

    brandLogoImg.onload = null;

    brandLogoImg.onerror = null;

  };

  brandLogoImg.onerror = () => {

    brandLogoImg.hidden = true;

    brandLogoImg.removeAttribute("src");

    brandGroup.classList.remove("brand-group--with-logo");

    brandLogoFallback.hidden = false;

    brandLogoImg.onload = null;

    brandLogoImg.onerror = null;

  };

  brandLogoImg.alt = `Logo de ${resolvedTitle}`;

  brandLogoImg.src = logoUrl;

}



function resetMetrics() {

  if (!metricGrid) return;

  metricGrid.innerHTML = "";

  if (metricPlaceholder) {

    metricPlaceholder.textContent = "Selecciona variables y ejecuta la consulta para ver mtricas.";

    metricGrid.appendChild(metricPlaceholder);

  }

}



function formatNumber(value) {

  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";

  const abs = Math.abs(Number(value));

  if (abs >= 1000 || abs === 0) return Number(value).toFixed(2);

  if (abs >= 1) return Number(value).toFixed(3);

  return Number(value).toPrecision(3);

}



function updateMetrics(seriesCollection) {

  if (!metricGrid) return;

  metricGrid.innerHTML = "";

  if (!seriesCollection.length) {

    resetMetrics();

    return;

  }



  const fragment = document.createDocumentFragment();

  seriesCollection.forEach((entry) => {

    const card = document.createElement("article");

    card.className = "metric-card";



    const label = document.createElement("span");

    label.className = "metric-label";

    label.textContent = entry.tag;

    card.appendChild(label);



    if (!entry.stats) {

      const empty = document.createElement("p");

      empty.className = "helper-text";

      empty.textContent = "Sin datos en el rango consultado.";

      card.appendChild(empty);

    } else {

      const latest = document.createElement("strong");

      latest.textContent = `ltimo: ${formatNumber(entry.stats.latest)}`;

      card.appendChild(latest);



      const extremes = document.createElement("p");

      extremes.className = "helper-text";

      extremes.textContent = `Min ${formatNumber(entry.stats.min)} - Max ${formatNumber(entry.stats.max)} - Prom ${formatNumber(entry.stats.avg)}`;

      card.appendChild(extremes);



      const ts = document.createElement("p");

      ts.className = "helper-text";

      ts.textContent = entry.stats.latestTimestamp ? `Actualizado: ${new Date(entry.stats.latestTimestamp).toLocaleString()}` : "Sin timestamp disponible.";

      card.appendChild(ts);

    }

    fragment.appendChild(card);

  });



  metricGrid.appendChild(fragment);

}



function ensureChart() {

  if (chartInstance) return chartInstance;

  chartInstance = new Chart(trendCanvas, {

    type: "line",

    data: { datasets: [] },

    options: {

      responsive: true,

      maintainAspectRatio: false,

      parsing: false,

      scales: {

        x: {

          type: "time",

          time: {

            tooltipFormat: "yyyy-MM-dd HH:mm",

            unit: "hour",

          },

        },

        y: {

          ticks: {

            precision: 3,

          },

        },

      },

      plugins: {

        legend: {

          display: true,

          position: "bottom",

        },

        tooltip: {

          callbacks: {

            label(context) {

              const value = context.parsed.y;

              return `${context.dataset.label}: ${formatNumber(value)}`;

            },

          },

        },

      },

    },

  });

  return chartInstance;

}



function updateTimeScale(fromIso, toIso) {

  const chart = ensureChart();

  let min = fromIso ? new Date(fromIso) : null;

  let max = toIso ? new Date(toIso) : null;

  if (min && Number.isNaN(min.getTime())) min = null;

  if (max && Number.isNaN(max.getTime())) max = null;



  if (min && max) {

    const diffHours = Math.max((max - min) / 36e5, 0.01);

    let unit = "day";

    if (diffHours <= 1) {

      unit = "minute";

    } else if (diffHours <= 12) {

      unit = "hour";

    } else if (diffHours <= 24 * 7) {

      unit = "day";

    } else if (diffHours <= 24 * 30) {

      unit = "week";

    } else {

      unit = "month";

    }

    chart.options.scales.x.time.unit = unit;

    chart.options.scales.x.min = min;

    chart.options.scales.x.max = max;

  } else {

    chart.options.scales.x.time.unit = "day";

    delete chart.options.scales.x.min;

    delete chart.options.scales.x.max;

  }

}



function renderSeries(seriesCollection) {

  const chart = ensureChart();

  const palette = ["#00b4d8", "#fb8500", "#8338ec", "#ef476f", "#06d6a0", "#ffd166", "#3a86ff", "#ffbe0b"];



  const datasets = seriesCollection.map((entry, index) => {

    const color = palette[index % palette.length];

    return {

      label: entry.tag,

      data: (entry.points || []).map((point) => ({

        x: point.timestamp ? new Date(point.timestamp) : null,

        y: point.value,

      })),

      borderColor: color,

      backgroundColor: `${color}33`,

      tension: 0.15,

      pointRadius: 0,

      fill: true,

    };

  });



  chart.data.datasets = datasets;

  chart.update();



  lastSeriesCollection = seriesCollection;

  const hasPoints = seriesCollection.some((entry) => Array.isArray(entry.points) && entry.points.length);

  downloadCsvBtn.disabled = !hasPoints;

}



function toISOStringLocal(value) {

  if (!value) return null;

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return null;

  return date.toISOString();

}



async function withAuth(init = {}) {

  const user = firebase.auth().currentUser;

  if (!user) throw new Error("sesion no disponible");

  const token = await user.getIdToken();

  state.token = token;

  const headers = new Headers(init.headers || {});

  headers.set("Authorization", `Bearer ${token}`);

  headers.set("Accept", "application/json");

  return { ...init, headers };

}



async function fetchJson(url, init = {}) {

  const response = await fetch(url, await withAuth(init));

  if (response.status === 401) {

    const user = firebase.auth().currentUser;

    if (user) {

      await user.getIdToken(true);

      return fetchJson(url, init);

    }

  }

  if (!response.ok) {

    const text = await response.text();

    throw new Error(text || `Error HTTP ${response.status}`);

  }

  return response.json();

}



function computeRange(rangeValue) {

  const now = new Date();

  if (rangeValue === "custom") {

    const from = toISOStringLocal(fromInput.value);

    const to = toISOStringLocal(toInput.value) || now.toISOString();

    return { from, to };

  }



  const durations = {

    "15m": 15 * 60 * 1000,

    "30m": 30 * 60 * 1000,

    "1h": 60 * 60 * 1000,

    "24h": 24 * 60 * 60 * 1000,

    "48h": 48 * 60 * 60 * 1000,

    "7d": 7 * 24 * 60 * 60 * 1000,

  };

  const duration = durations[rangeValue] ?? durations["24h"];

  return {

    from: new Date(now.getTime() - duration).toISOString(),

    to: now.toISOString(),

  };

}



async function loadTags() {

  try {

    setApiStatus("Consultando tags...", false);

    setFormEnabled(false);

    showFeedback("Cargando variables disponibles...", "info");



    const payload = await fetchJson(TAGS_ENDPOINT);

    const tags = Array.isArray(payload?.tags) ? payload.tags : [];

    state.empresaId = payload?.empresaId || null;



    const title = hydrateMainTitle();

    updateBrandLogo(state.empresaId, title);



    tagSelect.innerHTML = "";

    if (!tags.length) {

      setApiStatus("Sin tags configurados", true);

      showFeedback("No hay tendencias configuradas para la empresa seleccionada.", "warning");

      return;

    }



    tags.forEach((tag) => {

      const option = document.createElement("option");

      option.value = tag;

      option.textContent = tag;

      tagSelect.appendChild(option);

    });



    tagSelect.multiple = true;

    tagSelect.size = Math.min(Math.max(tags.length, 4), 10);

    Array.from(tagSelect.options).forEach((option, index) => {

      option.selected = index === 0;

    });



    tagSelect.disabled = false;

    rangeSelect.disabled = false;

    resolutionSelect.disabled = false;

    runButton.disabled = false;



    setApiStatus("Tags disponibles", true);

    showFeedback("Selecciona una o varias variables y haz clic en Actualizar.", "info");

  } catch (error) {

    console.error("No se pudieron obtener los tags", error);

    setApiStatus("Error al consultar", false);

    showFeedback("No fue posible obtener la lista de tags. Intenta nuevamente.", "error");

  }

}



async function loadTrendData(event) {

  if (event) event.preventDefault();



  const tags = Array.from(tagSelect.selectedOptions || []).map((option) => option.value).filter(Boolean);

  if (!tags.length) {

    showFeedback("Selecciona al menos una variable para consultar.", "warning");

    return;

  }



  const rangeValue = rangeSelect.value || "24h";

  if (rangeValue === "custom" && (!fromInput.value || !toInput.value)) {

    showFeedback("Debes definir fecha de inicio y fin para el rango personalizado.", "warning");

    return;

  }



  const resolution = resolutionSelect.value || "raw";

  const { from, to } = computeRange(rangeValue);



  const params = new URLSearchParams({ resolution });

  tags.forEach((tag) => params.append("tag", tag));

  if (from) params.set("from", from);

  if (to) params.set("to", to);



  updateTimeScale(from, to);

  showFeedback("Cargando datos de tendencia...", "info");

  setApiStatus("Consultando...", true);

  resetMetrics();

  downloadCsvBtn.disabled = true;



  try {

    const payload = await fetchJson(`${API_BASE}?${params.toString()}`);

    const seriesCollection = Array.isArray(payload?.series) ? payload.series : [];

    const totalPoints = Number(payload?.meta?.totalPoints || 0);



    if (!seriesCollection.length || totalPoints === 0) {

      renderSeries([]);

      updateMetrics([]);

      setApiStatus("Sin datos en rango", true);

      showFeedback("No se encontraron registros para los filtros seleccionados.", "warning");

      return;

    }



    renderSeries(seriesCollection);

    updateMetrics(seriesCollection);



    const tagSummary = seriesCollection.map((entry) => entry.tag).join(", ");

    setApiStatus(`Registros: ${totalPoints}`, true);

    showFeedback(`Se recuperaron ${totalPoints} puntos para ${tagSummary}.`, "success");

  } catch (error) {

    console.error("No se pudo obtener la tendencia", error);

    setApiStatus("Error al cargar", false);

    showFeedback("Ocurri un error al obtener los datos. Vuelve a intentar.", "error");

  }

}



function exportCsv() {

  if (!lastSeriesCollection.length) return;

  const rows = [["tag", "timestamp", "value"]];

  lastSeriesCollection.forEach((entry) => {

    (entry.points || []).forEach((point) => {

      rows.push([entry.tag, point.timestamp, point.value]);

    });

  });

  if (rows.length === 1) return;



  const csvContent = rows
    .map((cols) => cols.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(","))
    .join("\r\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });

  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");

  const tagLabel = lastSeriesCollection.length === 1 ? lastSeriesCollection[0].tag : "tendencias";

  link.href = url;

  link.download = `${tagLabel}_${Date.now()}.csv`;

  document.body.appendChild(link);

  link.click();

  document.body.removeChild(link);

  URL.revokeObjectURL(url);

}



function toggleCustomRange() {

  const isCustom = rangeSelect.value === "custom";

  customRange.hidden = !isCustom;

  if (!isCustom) {

    fromInput.value = "";

    toInput.value = "";

  }

}



function setFormEnabled(enabled) {

  const controls = [tagSelect, rangeSelect, resolutionSelect, runButton, downloadCsvBtn];

  controls.forEach((control) => {

    if (!control) return;

    control.disabled = !enabled;

  });

  if (!enabled && tagSelect) {

    tagSelect.innerHTML = '<option value="">Selecciona una opcin</option>';

  }

}



function attachEventHandlers() {

  openLoginBtn?.addEventListener("click", () => {

    loginDialog?.showModal();

    emailInput?.focus();

  });



  closeLoginBtn?.addEventListener("click", () => {

    loginDialog?.close();

    if (emailInput) emailInput.value = "";

    if (passwordInput) passwordInput.value = "";

  });



  loginForm?.addEventListener("submit", async (event) => {

    event.preventDefault();

    const email = emailInput.value.trim();

    const password = passwordInput.value;

    if (!email || !password) return;

    setStatus("Iniciando sesion...");

    try {

      await firebase.auth().signInWithEmailAndPassword(email, password);

      loginDialog?.close();

      emailInput.value = "";

      passwordInput.value = "";

    } catch (error) {

      console.error("No se pudo iniciar sesion", error);

      setStatus("Error al iniciar sesion");

    }

  });



  logoutBtn?.addEventListener("click", async () => {

    try {

      await firebase.auth().signOut();

    } catch (error) {

      console.error("Error al cerrar sesion", error);

    }

  });



  rangeSelect?.addEventListener("change", toggleCustomRange);

  trendForm?.addEventListener("submit", loadTrendData);

  downloadCsvBtn?.addEventListener("click", exportCsv);



  firebase.auth().onAuthStateChanged((user) => {

    state.user = user;

    if (user) {

      const resolvedTitle = hydrateMainTitle();

      updateBrandLogo(state.empresaId, resolvedTitle);

      setStatus(`sesion activa: ${user.email}`);

      currentUserLabel.textContent = user.email || "Usuario autenticado";

      logoutBtn.disabled = false;

      openLoginBtn.disabled = true;

      loadTags();

    } else {

      setStatus("Sin sesion");

      currentUserLabel.textContent = "Annimo";

      currentCompanyLabel.hidden = true;

      logoutBtn.disabled = true;

      openLoginBtn.disabled = false;

      setApiStatus("Sin conexin", false);

      setFormEnabled(false);

      renderSeries([]);

      updateMetrics([]);

      resetMetrics();

      showFeedback("Inicia sesion para consultar datos histricos.", "info");

      updateBrandLogo(null, DEFAULT_MAIN_TITLE);

      document.title = DEFAULT_MAIN_TITLE;

    }

  });



  document.addEventListener("visibilitychange", async () => {

    if (document.visibilityState === "visible" && firebase.auth().currentUser) {

      try {

        await firebase.auth().currentUser.getIdToken(true);

      } catch (error) {

        console.warn("No se pudo refrescar el token", error);

      }

    }

  });

}



function initialize() {

  hydrateMainTitle();

  toggleCustomRange();

  setFormEnabled(false);

  resetMetrics();

  renderSeries([]);

  showFeedback("Inicia sesion para comenzar.", "info");

  attachEventHandlers();

}



initialize();

