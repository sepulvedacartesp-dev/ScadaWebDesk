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
const tempGaugesRoot = document.getElementById("demo-temp-gauges");
const tempTrendPaths = [
  document.getElementById("demo-temp-line-a"),
  document.getElementById("demo-temp-line-b"),
  document.getElementById("demo-temp-line-c"),
];
const tempCurrentLabels = [
  document.getElementById("demo-temp-current-a"),
  document.getElementById("demo-temp-current-b"),
  document.getElementById("demo-temp-current-c"),
];

const TICK_MS = 600;
const FILL_PER_TICK = 3.2;
const DRAIN_PER_TICK = 1.4;
const HISTORY_LENGTH = 28;
const CHART_WIDTH = 220;
const CHART_HEIGHT = 120;
const TEMP_MIN = 0;
const TEMP_MAX = 150;
const TEMP_HISTORY_LENGTH = 36;
const TEMP_CHART_WIDTH = 220;
const TEMP_CHART_HEIGHT = 120;
const TEMP_COLORS = ["#3a86ff", "#ffd166", "#ef476f"];
const INITIAL_TEMPERATURES = [62, 68, 64];

const state = {
  pumpOn: false,
  level: 0,
  lastTick: Date.now(),
  timer: null,
};
const trendHistory = Array(HISTORY_LENGTH).fill(0);
const temperatureState = {
  values: INITIAL_TEMPERATURES.slice(),
  history: INITIAL_TEMPERATURES.map((value) => Array(TEMP_HISTORY_LENGTH).fill(value)),
};
const tempGauges = [];

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

function createTemperatureGauge({ id, label, color, min = TEMP_MIN, max = TEMP_MAX, unit = "\u00B0C" }) {
  const wrapper = document.createElement("div");
  wrapper.className = "gauge-container demo-temp-gauge";
  if (color) {
    wrapper.style.setProperty("--gauge-accent", color);
  }

  const dial = document.createElement("div");
  dial.className = "gauge-dial";
  const tickSteps = 10;
  for (let i = 0; i <= tickSteps; i += 1) {
    const tick = document.createElement("span");
    tick.className = "gauge-tick";
    if (i % 5 === 0) {
      tick.classList.add("is-major");
    }
    const rotation = -90 + (i / tickSteps) * 180;
    tick.style.transform = `rotate(${rotation}deg) translateY(-6%)`;
    dial.appendChild(tick);
  }

  const needle = document.createElement("div");
  needle.className = "gauge-needle";
  dial.appendChild(needle);

  const center = document.createElement("div");
  center.className = "gauge-center";
  dial.appendChild(center);

  const scale = document.createElement("div");
  scale.className = "gauge-scale";
  const minLabel = document.createElement("span");
  minLabel.textContent = min.toFixed(0);
  const maxLabel = document.createElement("span");
  maxLabel.textContent = max.toFixed(0);
  scale.append(minLabel, maxLabel);

  const info = document.createElement("div");
  info.className = "gauge-info";
  const labelEl = document.createElement("div");
  labelEl.className = "gauge-label";
  labelEl.textContent = label;
  const reading = document.createElement("div");
  reading.className = "gauge-reading";
  const valueEl = document.createElement("span");
  valueEl.className = "gauge-value";
  valueEl.id = `${id}-value`;
  valueEl.textContent = "0.0";
  const unitEl = document.createElement("span");
  unitEl.className = "gauge-unit";
  unitEl.textContent = unit;
  reading.append(valueEl, unitEl);
  info.append(labelEl, reading);

  wrapper.append(dial, scale, info);

  const span = Math.max(max - min, 1);

  return {
    element: wrapper,
    update: (value) => {
      const numeric = parseFloat(value);
      if (!Number.isFinite(numeric)) return;
      const clamped = clamp(numeric, min, max);
      const ratio = (clamped - min) / span;
      const angle = ratio * 180 - 90;
      needle.style.transform = `rotate(${angle}deg)`;
      valueEl.textContent = clamped.toFixed(1);
    },
  };
}

function recordTemperatureHistory() {
  temperatureState.history.forEach((series, index) => {
    series.push(temperatureState.values[index]);
    if (series.length > TEMP_HISTORY_LENGTH) {
      series.shift();
    }
  });
}

function updateTemperatureTrend() {
  if (!tempTrendPaths.length) return;
  const firstSeries = temperatureState.history[0];
  if (!firstSeries || !firstSeries.length) return;
  const length = firstSeries.length;
  const span = Math.max(TEMP_MAX - TEMP_MIN, 1);
  const step = length > 1 ? TEMP_CHART_WIDTH / (length - 1) : TEMP_CHART_WIDTH;

  temperatureState.history.forEach((series, index) => {
    const pathNode = tempTrendPaths[index];
    if (!pathNode) return;
    let path = "";
    series.forEach((value, pointIndex) => {
      const clamped = clamp(value, TEMP_MIN, TEMP_MAX);
      const ratio = (clamped - TEMP_MIN) / span;
      const x = pointIndex * step;
      const y = TEMP_CHART_HEIGHT - ratio * TEMP_CHART_HEIGHT;
      path += `${pointIndex === 0 ? "M" : "L"}${x} ${y} `;
    });
    pathNode.setAttribute("d", path.trim());
  });
}

function updateTemperatureVisuals() {
  temperatureState.values.forEach((value, index) => {
    if (tempGauges[index]) {
      tempGauges[index].update(value);
    }
    if (tempCurrentLabels[index]) {
      tempCurrentLabels[index].textContent = `${value.toFixed(1)} \u00B0C`;
    }
  });
  updateTemperatureTrend();
}

function updateTemperatures(elapsedTicks) {
  const multiplier = Math.max(1, elapsedTicks);
  temperatureState.values = temperatureState.values.map((value, index) => {
    const driftBase = state.pumpOn ? 0.85 : -0.35;
    const sensorOffset = index === 1 ? 0.2 : index === 2 ? -0.15 : 0;
    const noise = (Math.random() - 0.5) * 1.0;
    const next = value + (driftBase + sensorOffset + noise) * multiplier;
    return clamp(next, TEMP_MIN, TEMP_MAX);
  });
  recordTemperatureHistory();
  updateTemperatureVisuals();
}

function setupTemperaturePanel() {
  if (!tempGaugesRoot) return;
  tempGaugesRoot.innerHTML = "";
  tempGauges.length = 0;
  const configs = [
    { id: "demo-temp-gauge-a", label: "Sensor A", color: TEMP_COLORS[0] },
    { id: "demo-temp-gauge-b", label: "Sensor B", color: TEMP_COLORS[1] },
    { id: "demo-temp-gauge-c", label: "Sensor C", color: TEMP_COLORS[2] },
  ];
  configs.forEach((config) => {
    const gauge = createTemperatureGauge(config);
    tempGaugesRoot.appendChild(gauge.element);
    tempGauges.push(gauge);
  });
  updateTemperatureVisuals();
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
  updateTemperatures(elapsedTicks);
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
  temperatureState.values = INITIAL_TEMPERATURES.slice();
  temperatureState.history = INITIAL_TEMPERATURES.map((value) =>
    Array(TEMP_HISTORY_LENGTH).fill(value)
  );
  updateTemperatureVisuals();
  updateVisuals();
  updateButtons();
}

function init() {
  if (!startBtn || !stopBtn || !resetBtn) return;
  setupTemperaturePanel();
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
