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

const metricLatest = document.getElementById("metric-latest");
const metricMin = document.getElementById("metric-min");
const metricMax = document.getElementById("metric-max");
const metricAvg = document.getElementById("metric-avg");

const downloadCsvBtn = document.getElementById("download-csv");
const trendCanvas = document.getElementById("trend-canvas");
const trendFeedback = document.getElementById("trend-feedback");

const DEFAULT_MAIN_TITLE = "SurNex SCADA";
let trendChart = null;
let lastSeries = [];

const state = {
  user: null,
  token: null,
  empresaId: null,
};

function setStatus(text) {
  if (statusLabel) statusLabel.textContent = text;
}

function computeBrandInitials(value) {
  if (!value) return "SW";
  const tokens = String(value)
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!tokens.length) return "SW";
  return tokens
    .slice(0, 2)
    .map((word) => (word && word[0] ? word[0].toUpperCase() : ""))
    .join("") || "SW";
}

function setBrandFallback(title) {
  if (!brandLogoFallback) return;
  const initials = computeBrandInitials(title);
  brandLogoFallback.textContent = initials;
  brandLogoFallback.hidden = false;
}

function clearBrandLogo(title) {
  const resolvedTitle = title || (mainTitleNode ? mainTitleNode.textContent : DEFAULT_MAIN_TITLE) || DEFAULT_MAIN_TITLE;
  if (brandLogoImg) {
    brandLogoImg.hidden = true;
    brandLogoImg.removeAttribute("src");
    brandLogoImg.alt = `Logo de ${resolvedTitle}`;
  }
  if (brandGroup) {
    brandGroup.classList.remove("brand-group--with-logo");
  }
  setBrandFallback(resolvedTitle);
}

let currentLogoEmpresa = null;
let currentLogoVersion = 0;

function updateBrandLogo(empresaId, { forceRefresh = false, title } = {}) {
  const resolvedTitle = title || (mainTitleNode ? mainTitleNode.textContent : DEFAULT_MAIN_TITLE) || DEFAULT_MAIN_TITLE;
  setBrandFallback(resolvedTitle);
  if (!brandLogoImg || !brandGroup) return;
  if (!empresaId) {
    clearBrandLogo(resolvedTitle);
    return;
  }
  if (forceRefresh || currentLogoEmpresa !== empresaId) {
    currentLogoEmpresa = empresaId;
    currentLogoVersion = Date.now();
  }
  const url = `${BACKEND_HTTP}/logos/${encodeURIComponent(empresaId)}.jpg?v=${currentLogoVersion}`;
  brandLogoImg.onload = () => {
    brandLogoImg.hidden = false;
    brandLogoImg.alt = `Logo de ${resolvedTitle}`;
    brandGroup.classList.add("brand-group--with-logo");
    if (brandLogoFallback) {
      brandLogoFallback.hidden = true;
    }
    brandLogoImg.onload = null;
    brandLogoImg.onerror = null;
  };
  brandLogoImg.onerror = () => {
    brandLogoImg.hidden = true;
    brandLogoImg.removeAttribute("src");
    brandGroup.classList.remove("brand-group--with-logo");
    setBrandFallback(resolvedTitle);
    brandLogoImg.onload = null;
    brandLogoImg.onerror = null;
  };
  brandLogoImg.src = url;
}

function setApiStatus(connected, message) {
  if (!apiStatusChip) return;
  apiStatusChip.textContent = message || (connected ? "Datos disponibles" : "Sin conexión");
  apiStatusChip.classList.toggle("chip-connected", connected);
  apiStatusChip.classList.toggle("chip-disconnected", !connected);
}

function setFormEnabled(enabled) {
  const controls = [tagSelect, rangeSelect, resolutionSelect, runButton, downloadCsvBtn];
  controls.forEach((ctrl) => {
    if (!ctrl) return;
    ctrl.disabled = !enabled;
  });
  if (!enabled) {
    tagSelect.innerHTML = '<option value="">Selecciona una opción</option>';
  }
}

function resetMetrics() {
  metricLatest.textContent = "--";
  metricMin.textContent = "--";
  metricMax.textContent = "--";
  metricAvg.textContent = "--";
}

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const absVal = Math.abs(value);
  if (absVal >= 1000 || absVal === 0) {
    return Number(value).toFixed(2);
  }
  if (absVal >= 1) {
    return Number(value).toFixed(3);
  }
  return Number(value).toPrecision(3);
}

function updateMetrics(stats) {
  if (!stats) {
    resetMetrics();
    return;
  }
  metricLatest.textContent = formatNumber(stats.latest);
  metricMin.textContent = formatNumber(stats.min);
  metricMax.textContent = formatNumber(stats.max);
  metricAvg.textContent = formatNumber(stats.avg);
}

function showFeedback(message, tone = "info") {
  if (!trendFeedback) return;
  trendFeedback.textContent = message || "";
  trendFeedback.dataset.tone = tone;
}

function ensureChart() {
  if (trendChart) return trendChart;
  trendChart = new Chart(trendCanvas, {
    type: "line",
    data: {
      datasets: [
        {
          label: "Valor",
          data: [],
          borderColor: "#00b4d8",
          backgroundColor: "rgba(0, 180, 216, 0.15)",
          tension: 0.15,
          pointRadius: 0,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      scales: {
        x: {
          type: "time",
          time: {
            tooltipFormat: "yyyy-MM-dd HH:mm",
            displayFormats: {
              minute: "HH:mm",
              hour: "dd MMM HH:mm",
              day: "dd MMM",
            },
          },
          ticks: {
            source: "auto",
            major: { enabled: true },
          },
        },
        y: {
          ticks: {
            precision: 3,
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(context) {
              const value = context.parsed.y;
              return `Valor: ${formatNumber(value)}`;
            },
          },
        },
      },
    },
  });
  return trendChart;
}

function renderSeries(series) {
  const chart = ensureChart();
  const data = series.map((point) => ({
    x: point.timestamp ? new Date(point.timestamp) : null,
    y: point.value,
  }));
  chart.data.datasets[0].data = data;
  chart.update();
  lastSeries = series;
  downloadCsvBtn.disabled = !lastSeries.length;
}

function toISOStringLocal(inputValue) {
  if (!inputValue) return null;
  const date = new Date(inputValue);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

async function withAuthHeaders(init = {}) {
  const user = firebase.auth().currentUser;
  if (!user) throw new Error("Sesión finalizada");
  const token = await user.getIdToken();
  state.token = token;
  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("Accept", "application/json");
  return { ...init, headers };
}

async function fetchJson(url, init = {}) {
  const response = await fetch(url, await withAuthHeaders(init));
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

async function loadTags() {
  try {
    setApiStatus(false, "Consultando tags…");
    setFormEnabled(false);
    showFeedback("Cargando variables disponibles…", "info");
    const payload = await fetchJson(TAGS_ENDPOINT);
    const tags = Array.isArray(payload?.tags) ? payload.tags : [];
    state.empresaId = payload?.empresaId || null;
    if (currentCompanyLabel) {
      if (state.empresaId) {
        currentCompanyLabel.hidden = false;
        currentCompanyLabel.textContent = `Empresa: ${state.empresaId}`;
      } else {
        currentCompanyLabel.hidden = true;
      }
    }
    updateBrandLogo(state.empresaId, { forceRefresh: true });
    tagSelect.innerHTML = '<option value="">Selecciona una opción</option>';
    if (!tags.length) {
      setApiStatus(true, "Sin tags configurados");
      showFeedback("No hay tendencias configuradas para la empresa seleccionada.", "warning");
      return;
    }
    tags.forEach((tag) => {
      const option = document.createElement("option");
      option.value = tag;
      option.textContent = tag;
      tagSelect.appendChild(option);
    });
    tagSelect.disabled = false;
    rangeSelect.disabled = false;
    resolutionSelect.disabled = false;
    runButton.disabled = false;
    setApiStatus(true, "Tags disponibles");
    showFeedback("Selecciona un tag y actualiza para ver los datos.", "info");
    tagSelect.value = tags[0];
  } catch (error) {
    console.error("No se pudieron obtener los tags", error);
    setApiStatus(false, "Error al consultar");
    showFeedback("No fue posible obtener la lista de tags. Intenta nuevamente.", "error");
  }
}

function computeRange(rangeValue) {
  const now = new Date();
  let from = null;
  let to = now;
  if (rangeValue === "custom") {
    from = toISOStringLocal(fromInput.value);
    to = toISOStringLocal(toInput.value) || new Date().toISOString();
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
  from = new Date(now.getTime() - duration).toISOString();
  return { from, to: to.toISOString() };
}

async function loadTrendData() {
  const tag = tagSelect.value;
  if (!tag) {
    showFeedback("Selecciona una variable para consultar.", "warning");
    return;
  }
  const rangeValue = rangeSelect.value || "24h";
  if (rangeValue === "custom" && (!fromInput.value || !toInput.value)) {
    showFeedback("Debes definir fecha de inicio y fin para el rango personalizado.", "warning");
    return;
  }
  const resolution = resolutionSelect.value || "raw";
  const { from, to } = computeRange(rangeValue);
  const params = new URLSearchParams({ tag, resolution });
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  showFeedback("Cargando datos de tendencia…", "info");
  setApiStatus(true, "Consultando…");
  resetMetrics();
  downloadCsvBtn.disabled = true;
  try {
    const payload = await fetchJson(`${API_BASE}?${params.toString()}`);
    const series = Array.isArray(payload?.series) ? payload.series : [];
    if (!series.length) {
      renderSeries([]);
      updateMetrics(null);
      setApiStatus(true, "Sin datos en rango");
      showFeedback("No se encontraron registros para los filtros seleccionados.", "warning");
      return;
    }
    renderSeries(series);
    updateMetrics(payload?.stats);
    const count = series.length;
    setApiStatus(true, `Registros: ${count}`);
    showFeedback(`Se recuperaron ${count} puntos para ${tag}.`, "success");
  } catch (error) {
    console.error("No se pudo obtener la tendencia", error);
    setApiStatus(false, "Error al cargar");
    showFeedback("Ocurrió un error al obtener los datos. Vuelve a intentar.", "error");
  }
}

function exportCsv() {
  if (!lastSeries.length) return;
  const rows = [["timestamp", "value"]];
  lastSeries.forEach((point) => rows.push([point.timestamp, point.value]));
  const csvContent = rows.map((cols) => cols.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const tag = tagSelect.value || "trend";
  link.href = url;
  link.download = `${tag}_${Date.now()}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function onAuthStateChanged(user) {
  state.user = user;
  if (user) {
    setStatus(`Sesión activa: ${user.email}`);
    currentUserLabel.textContent = user.email || "Usuario autenticado";
    logoutBtn.disabled = false;
    openLoginBtn.disabled = true;
    loadTags();
  } else {
    setStatus("Sin sesión");
    currentUserLabel.textContent = "Anónimo";
    currentCompanyLabel.hidden = true;
    logoutBtn.disabled = true;
    openLoginBtn.disabled = false;
    setApiStatus(false, "Sin conexión");
    setFormEnabled(false);
    renderSeries([]);
    updateMetrics(null);
    showFeedback("Inicia sesión para consultar datos históricos.", "info");
    clearBrandLogo();
  }
}

function toggleCustomRange() {
  const isCustom = rangeSelect.value === "custom";
  customRange.hidden = !isCustom;
  if (!isCustom) {
    fromInput.value = "";
    toInput.value = "";
  }
}

openLoginBtn?.addEventListener("click", () => {
  loginDialog?.showModal();
  emailInput?.focus();
});

closeLoginBtn?.addEventListener("click", () => {
  loginDialog?.close();
  emailInput.value = "";
  passwordInput.value = "";
});

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = emailInput.value.trim();
  const password = passwordInput.value;
  if (!email || !password) return;
  setStatus("Iniciando sesión…");
  try {
    await firebase.auth().signInWithEmailAndPassword(email, password);
    loginDialog?.close();
    emailInput.value = "";
    passwordInput.value = "";
  } catch (error) {
    console.error("No se pudo iniciar sesión", error);
    setStatus("Error al iniciar sesión");
  }
});

logoutBtn?.addEventListener("click", async () => {
  try {
    await firebase.auth().signOut();
  } catch (error) {
    console.error("Error al cerrar sesión", error);
  }
});

rangeSelect?.addEventListener("change", toggleCustomRange);

trendForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  loadTrendData();
});

downloadCsvBtn?.addEventListener("click", exportCsv);

firebase.auth().onAuthStateChanged(onAuthStateChanged);

document.addEventListener("visibilitychange", async () => {
  if (document.visibilityState === "visible" && firebase.auth().currentUser) {
    try {
      await firebase.auth().currentUser.getIdToken(true);
    } catch (error) {
      console.warn("No se pudo refrescar el token", error);
    }
  }
});

// Estado inicial
setFormEnabled(false);
resetMetrics();
renderSeries([]);
showFeedback("Inicia sesión para comenzar.", "info");
toggleCustomRange();
