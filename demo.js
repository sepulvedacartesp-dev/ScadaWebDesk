const statusChip = document.getElementById("demo-status");
const heroLevel = document.getElementById("demo-level-hero");
const levelReadout = document.getElementById("demo-level");
const tankFill = document.getElementById("demo-tank-fill");
const tankIndicator = document.getElementById("demo-tank-indicator");
const pumpChip = document.getElementById("demo-pump-chip");
const flowReadout = document.getElementById("demo-flow");
const startBtn = document.getElementById("demo-start");
const stopBtn = document.getElementById("demo-stop");
const resetBtn = document.getElementById("demo-reset");
const containerCard = document.querySelector(".demo-container");
const pumpStatusLabel = document.getElementById("demo-pump-status-label");
const pumpIndicatorNode = document.getElementById("demo-pump-indicator");
const statusBadge = document.getElementById("demo-status-badge");
const statusMessage = document.getElementById("demo-status-message");
const trendArea = document.getElementById("demo-trend-area");
const trendLine = document.getElementById("demo-trend-line");
const trendCurrent = document.getElementById("demo-trend-current");
const trendMax = document.getElementById("demo-trend-max");
const trendMin = document.getElementById("demo-trend-min");

const TICK_MS = 600;
const FILL_PER_TICK = 3.2;
const DRAIN_PER_TICK = 1.4;
const HISTORY_LENGTH = 28;
const CHART_WIDTH = 220;
const CHART_HEIGHT = 120;

const state = {
  pumpOn: false,
  level: 0,
  lastTick: Date.now(),
  timer: null,
};
const trendHistory = Array(HISTORY_LENGTH).fill(0);

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatLevel(level) {
  return `${Math.round(level)}%`;
}

function formatFlow(pumpOn) {
  if (!pumpOn) return "0.0 m3/h";
  const value = 14 + Math.random() * 4;
  return `${value.toFixed(1)} m3/h`;
}

function setStatusMessage(text) {
  if (statusMessage) {
    statusMessage.textContent = text;
  }
}

function setStatusChip(text, isActive) {
  if (!statusChip) return;
  statusChip.textContent = text;
  statusChip.classList.toggle("chip-connected", isActive);
  statusChip.classList.toggle("chip-disconnected", !isActive);
}

function setPumpChip(text, isActive) {
  if (!pumpChip) return;
  pumpChip.textContent = text;
  pumpChip.classList.toggle("chip-connected", isActive);
  pumpChip.classList.toggle("chip-disconnected", !isActive);
}

function setPumpBadge(text, isActive) {
  if (!statusBadge) return;
  statusBadge.textContent = text;
  statusBadge.classList.toggle("chip-connected", isActive);
  statusBadge.classList.toggle("chip-disconnected", !isActive);
}

function updateButtons() {
  if (!startBtn || !stopBtn || !resetBtn) return;
  startBtn.disabled = state.pumpOn;
  stopBtn.disabled = !state.pumpOn;
  resetBtn.disabled = state.pumpOn || state.level === 0;
}

function recordHistory(level) {
  trendHistory.push(level);
  if (trendHistory.length > HISTORY_LENGTH) {
    trendHistory.shift();
  }
}

function updateTrend() {
  if (!trendArea || !trendLine) return;
  if (!trendHistory.length) return;
  const values = trendHistory;
  const width = CHART_WIDTH;
  const height = CHART_HEIGHT;
  const step = values.length > 1 ? width / (values.length - 1) : width;

  let areaPath = `M0 ${height}`;
  let linePath = "";

  values.forEach((value, index) => {
    const x = index * step;
    const y = height - (value / 100) * height;
    if (index === 0) {
      linePath = `M${x} ${y}`;
      areaPath += ` L${x} ${y}`;
    } else {
      linePath += ` L${x} ${y}`;
      areaPath += ` L${x} ${y}`;
    }
  });

  areaPath += ` L${(values.length - 1) * step} ${height} Z`;

  trendArea.setAttribute("d", areaPath);
  trendLine.setAttribute("d", linePath);

  if (trendCurrent) {
    trendCurrent.textContent = formatLevel(values[values.length - 1]);
  }
  if (trendMax) {
    trendMax.textContent = formatLevel(Math.max(...values));
  }
  if (trendMin) {
    trendMin.textContent = formatLevel(Math.min(...values));
  }
}

function updateVisuals() {
  const levelText = formatLevel(state.level);
  if (heroLevel) heroLevel.textContent = levelText;
  if (levelReadout) levelReadout.textContent = levelText;
  if (tankIndicator) tankIndicator.textContent = levelText;
  if (tankFill) tankFill.style.height = `${state.level}%`;

  const pumpOn = state.pumpOn;
  setPumpChip(pumpOn ? "Bomba funcionando" : "Bomba detenida", pumpOn);
  setPumpBadge(pumpOn ? "Funcionando" : "Detenida", pumpOn);

  if (pumpStatusLabel) {
    pumpStatusLabel.textContent = pumpOn ? "Funcionando" : "Detenida";
  }

  if (pumpIndicatorNode) {
    pumpIndicatorNode.classList.toggle("is-on", pumpOn);
    pumpIndicatorNode.classList.toggle("is-alert", !pumpOn && state.level >= 95);
  }

  if (flowReadout) {
    flowReadout.textContent = formatFlow(pumpOn);
  }

  if (containerCard) {
    containerCard.classList.toggle("demo-container--active", pumpOn);
    containerCard.classList.toggle("demo-container--alert", state.level >= 98);
  }

  updateTrend();
}

function tick() {
  const now = Date.now();
  const elapsedTicks = Math.max(1, Math.floor((now - state.lastTick) / TICK_MS));
  state.lastTick = now;

  let delta = 0;
  if (state.pumpOn) {
    delta = (FILL_PER_TICK + Math.random() * 0.6) * elapsedTicks;
  } else if (state.level > 0) {
    delta = -(DRAIN_PER_TICK + Math.random() * 0.4) * elapsedTicks;
  }

  state.level = clamp(state.level + delta, 0, 100);
  if (state.level >= 100 && state.pumpOn) {
    state.pumpOn = false;
    setStatusChip("Nivel alto - bomba detenida", false);
    setStatusMessage("Nivel alto alcanzado. Bomba detenida automaticamente.");
  }

  recordHistory(state.level);
  updateVisuals();
  updateButtons();
}

function startSimulation() {
  if (state.pumpOn) return;
  state.pumpOn = true;
  state.lastTick = Date.now();
  setStatusChip("Simulacion activa", true);
  setStatusMessage("Operador inicia bomba BP-7.");
  updateButtons();
  updateVisuals();
}

function stopSimulation(manual = true) {
  if (!state.pumpOn) return;
  state.pumpOn = false;
  setStatusChip("Simulacion en pausa", false);
  if (manual) {
    setStatusMessage("Operador detiene bomba BP-7.");
  }
  updateButtons();
  updateVisuals();
}

function resetSimulation() {
  if (state.pumpOn) return;
  state.level = 0;
  setStatusChip("En espera", false);
  trendHistory.fill(0);
  setStatusMessage("Variables reiniciadas. Estanque en nivel base.");
  updateVisuals();
  updateButtons();
}

function init() {
  if (!startBtn || !stopBtn || !resetBtn) return;
  trendHistory.fill(state.level);
  updateVisuals();
  updateButtons();
  setStatusMessage("Simulacion lista. Esperando accion del operador.");

  startBtn.addEventListener("click", () => {
    startSimulation();
  });

  stopBtn.addEventListener("click", () => {
    stopSimulation(true);
  });

  resetBtn.addEventListener("click", () => {
    resetSimulation();
  });

  state.timer = setInterval(() => {
    tick();
    if (!state.pumpOn && state.level <= 0) {
      setStatusChip("En espera", false);
    }
  }, TICK_MS);

  window.addEventListener("beforeunload", () => {
    if (state.timer) clearInterval(state.timer);
  });
}

document.addEventListener("DOMContentLoaded", init);
