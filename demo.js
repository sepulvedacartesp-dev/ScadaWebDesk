const statusChip = document.getElementById("demo-status");
const heroLevel = document.getElementById("demo-level-hero");
const levelReadout = document.getElementById("demo-level");
const tankFill = document.getElementById("demo-tank-fill");
const tankIndicator = document.getElementById("demo-tank-indicator");
const pumpChip = document.getElementById("demo-pump-chip");
const pumpStatus = document.getElementById("demo-pump-status");
const pumpDescription = document.getElementById("demo-pump-description");
const flowReadout = document.getElementById("demo-flow");
const logList = document.getElementById("demo-log-list");
const startBtn = document.getElementById("demo-start");
const stopBtn = document.getElementById("demo-stop");
const resetBtn = document.getElementById("demo-reset");
const containerCard = document.querySelector(".demo-container");

const TICK_MS = 600;
const FILL_PER_TICK = 3.2;
const DRAIN_PER_TICK = 1.4;
const MAX_LOG_ITEMS = 6;

const state = {
  pumpOn: false,
  level: 0,
  lastTick: Date.now(),
  timer: null,
};

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatLevel(level) {
  return `${Math.round(level)}%`;
}

function formatFlow(pumpOn) {
  if (!pumpOn) return "0.0 m³/h";
  const value = 14 + Math.random() * 4;
  return `${value.toFixed(1)} m³/h`;
}

function appendLog(message) {
  if (!logList) return;
  const time = new Date();
  const timestamp = time.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const item = document.createElement("li");
  item.textContent = `[${timestamp}] ${message}`;
  logList.prepend(item);
  while (logList.children.length > MAX_LOG_ITEMS) {
    logList.removeChild(logList.lastElementChild);
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

function updateButtons() {
  if (!startBtn || !stopBtn || !resetBtn) return;
  startBtn.disabled = state.pumpOn;
  stopBtn.disabled = !state.pumpOn;
  resetBtn.disabled = state.pumpOn || state.level === 0;
}

function updateVisuals() {
  const levelText = formatLevel(state.level);
  if (heroLevel) heroLevel.textContent = levelText;
  if (levelReadout) levelReadout.textContent = levelText;
  if (tankIndicator) tankIndicator.textContent = levelText;
  if (tankFill) tankFill.style.height = `${state.level}%`;

  const pumpOn = state.pumpOn;
  setPumpChip(pumpOn ? "Bomba en marcha" : "Bomba detenida", pumpOn);
  if (pumpStatus) pumpStatus.textContent = pumpOn ? "En operación" : state.level > 0 ? "En pausa" : "Detenida";

  if (pumpDescription) {
    if (pumpOn) {
      pumpDescription.textContent = state.level >= 98 ? "Estanque en nivel alto. Evaluar detener la bomba." : "Bomba energizada. Supervisando presión y flujo.";
    } else if (state.level > 0) {
      pumpDescription.textContent = "Estanque estabilizado. La bomba puede arrancar si se requiere reposición.";
    } else {
      pumpDescription.textContent = "Lista para iniciar. No hay consumo de energía.";
    }
  }

  if (flowReadout) {
    flowReadout.textContent = formatFlow(pumpOn);
  }

  if (containerCard) {
    containerCard.classList.toggle("demo-container--active", pumpOn);
    containerCard.classList.toggle("demo-container--alert", state.level >= 98);
  }
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

  const previousLevel = state.level;
  state.level = clamp(state.level + delta, 0, 100);
  if (state.level >= 100 && state.pumpOn) {
    state.pumpOn = false;
    setStatusChip("Nivel alto - bomba detenida", false);
    appendLog("Nivel alto alcanzado. Bomba detenida automáticamente.");
  }

  if (previousLevel !== state.level) {
    updateVisuals();
  }

  updateButtons();
}

function startSimulation() {
  if (state.pumpOn) return;
  state.pumpOn = true;
  state.lastTick = Date.now();
  setStatusChip("Simulación activa", true);
  appendLog("Operador inicia bomba BP-7.");
  updateButtons();
  updateVisuals();
}

function stopSimulation(manual = true) {
  if (!state.pumpOn) return;
  state.pumpOn = false;
  setStatusChip("Simulación en pausa", false);
  if (manual) {
    appendLog("Operador detiene bomba BP-7.");
  }
  updateButtons();
  updateVisuals();
}

function resetSimulation() {
  if (state.pumpOn) return;
  state.level = 0;
  setStatusChip("En espera", false);
  appendLog("Variables reiniciadas. Estanque en nivel base.");
  updateVisuals();
  updateButtons();
}

function init() {
  if (!startBtn || !stopBtn || !resetBtn) return;
  updateVisuals();
  updateButtons();
  appendLog("Simulación lista. Esperando acción del operador.");

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
