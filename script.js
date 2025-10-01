const BACKEND_HTTP = "https://scadawebdesk.onrender.com";
const BACKEND_WS = "wss://scadawebdesk.onrender.com/ws";

let ws = null;
let uid = null;
let reconnectTimer = null;
let lastToken = null;
let scadaConfig = null;
let currentRole = "viewer";
let currentView = "matrix";

const loginForm = document.getElementById("login-form");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const statusLabel = document.getElementById("status");
const logArea = document.getElementById("log");
const logoutBtn = document.getElementById("logout-btn");
const openLoginBtn = document.getElementById("open-login");
const closeLoginBtn = document.getElementById("close-login");
const loginDialog = document.getElementById("login-dialog");
const connectChip = document.getElementById("connect-status");
const configLink = document.getElementById("config-link");
const currentUserLabel = document.getElementById("current-user");
const scadaContainer = document.getElementById("scada-container");
const viewMatrixBtn = document.getElementById("view-matrix");
const viewSidebarBtn = document.getElementById("view-sidebar");
const sidebarMenu = document.getElementById("sidebar-menu");

const topicElementMap = new Map();
const topicStateCache = new Map();
const controlElements = new Set();
const widgetBindings = [];

function setStatus(text) {
  if (statusLabel) {
    statusLabel.textContent = text;
  }
}

function appendLog(entry) {
  if (!logArea) return;
  const now = new Date().toISOString();
  logArea.textContent += '[' + now + '] ' + entry + '\n';
  logArea.scrollTop = logArea.scrollHeight;
}

function normalizeRelativePath(relPath) {
  return relPath.split("/").filter(Boolean).join("/");
}

function scopedTopic(relative) {
  if (!uid) return null;
  return `scada/customers/${uid}/${normalizeRelativePath(relative)}`;
}

async function login(email, password) {
  setStatus("Iniciando sesión...");
  await firebase.auth().signInWithEmailAndPassword(email, password);
  setStatus("Sesión iniciada, conectando...");
}

function disconnectWs(reason) {
  if (ws) {
    ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
    try { ws.close(); } catch (_) { /* ignore */ }
  }
  ws = null;
  updateConnectionChip(false);
  if (reason) {
    appendLog(`WS cerrado (${reason})`);
  }
}

function updateConnectionChip(isConnected) {
  if (!connectChip) return;
  connectChip.textContent = isConnected ? "Conectado" : "Desconectado";
  connectChip.classList.toggle("chip-connected", isConnected);
  connectChip.classList.toggle("chip-disconnected", !isConnected);
}

async function connectWs(user) {
  if (!user) return;
  try {
    const idToken = await user.getIdToken();
    if (idToken === lastToken && ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    lastToken = idToken;
    disconnectWs();

    const url = `${BACKEND_WS}?token=${encodeURIComponent(idToken)}`;
    ws = new WebSocket(url);

    ws.onopen = () => {
      appendLog("WS abierto");
      updateConnectionChip(true);
      setStatus(`Conectado como ${user.email}`);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "hello") {
          handleHello(msg);
        } else if (msg.type === "ack") {
          appendLog(`ACK ${msg.topic}`);
        } else if (msg.type === "error") {
          appendLog(`ERROR ${msg.error}`);
        } else if (msg.topic) {
          handleTopicMessage(msg);
        }
      } catch (err) {
        appendLog(`Mensaje WS inválido: ${err}`);
      }
    };

    ws.onclose = (event) => {
      appendLog(`WS cerrado codigo=${event.code}`);
      ws = null;
      updateConnectionChip(false);
      if (firebase.auth().currentUser) {
        scheduleReconnect();
      } else {
        setStatus("Sesión cerrada");
      }
    };

    ws.onerror = (err) => {
      appendLog(`WS error ${err.message || err}`);
    };
  } catch (error) {
    appendLog(`No se pudo abrir WS: ${error.message || error}`);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    const user = firebase.auth().currentUser;
    if (user) {
      connectWs(user);
    }
  }, 5000);
}

function handleHello(msg) {
  uid = msg.uid;
  appendLog(`HELLO uid=${uid}`);
  applyScopedTopics();
}

function handleTopicMessage({ topic, payload }) {
  topicStateCache.set(topic, payload);
  const handlers = topicElementMap.get(topic);
  if (handlers) {
    handlers.forEach((updateFn) => {
      try {
        updateFn(payload);
      } catch (err) {
        console.error("Error actualizando widget", err);
      }
    });
  }
}

function applyScopedTopics() {
  topicElementMap.clear();
  if (!uid) return;
  widgetBindings.forEach((binding) => {
    const fullTopic = scopedTopic(binding.topic);
    if (!fullTopic) return;
    if (!topicElementMap.has(fullTopic)) {
      topicElementMap.set(fullTopic, []);
    }
    topicElementMap.get(fullTopic).push(binding.update);
    const cached = topicStateCache.get(fullTopic);
    if (cached !== undefined) {
      binding.update(cached);
    }
  });
}

function updateRoleUI() {
  const isAdmin = currentRole === "admin";
  const isViewer = currentRole === "viewer" || currentRole === "visualizacion";

  if (configLink) {
    configLink.hidden = !isAdmin;
  }
  controlElements.forEach((btn) => {
    if (isViewer) {
      btn.setAttribute("disabled", "");
      btn.classList.add("control-disabled");
    } else {
      btn.removeAttribute("disabled");
      btn.classList.remove("control-disabled");
    }
  });
}

function setCurrentUser(email) {
  currentUserLabel.textContent = email || "Anónimo";
}

function determineRole(email) {
  if (!scadaConfig || !email) return "operador";
  const roles = scadaConfig.roles || {};
  if (Array.isArray(roles.admins) && roles.admins.includes(email)) return "admin";
  if (Array.isArray(roles.operators) && roles.operators.includes(email)) return "operador";
  if (Array.isArray(roles.viewers) && roles.viewers.includes(email)) return "visualizacion";
  return "operador";
}

async function loadScadaConfig() {
  if (scadaConfig) return scadaConfig;
  const response = await fetch("scada_config.json", { cache: "no-cache" });
  if (!response.ok) {
    throw new Error("No se pudo cargar scada_config.json");
  }
  const data = await response.json();
  scadaConfig = data;
  return scadaConfig;
}

function clearDashboard() {
  widgetBindings.length = 0;
  controlElements.clear();
  topicElementMap.clear();
  scadaContainer.innerHTML = "";
  if (sidebarMenu) {
    sidebarMenu.innerHTML = "";
    sidebarMenu.hidden = false;
  }
}

function renderDashboard() {
  if (!scadaConfig || !Array.isArray(scadaConfig.containers)) {
    scadaContainer.innerHTML = "<p>No hay configuración disponible.</p>";
    return;
  }

  const template = document.getElementById("container-template");
  scadaContainer.classList.toggle("sidebar-view", currentView === "sidebar");
  scadaConfig.containers.forEach((container, index) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const titleEl = node.querySelector(".container-title");
    const bodyEl = node.querySelector(".container-body");
    if (titleEl) titleEl.textContent = container.title || `Contenedor ${index + 1}`;

    const navButton = document.createElement("button");
    navButton.textContent = container.title || `Contenedor ${index + 1}`;
    navButton.addEventListener("click", () => {
      node.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    sidebarMenu.appendChild(navButton);

    (container.objects || []).forEach((objectDef, objIndex) => {
      const widget = buildWidget(objectDef, index, objIndex);
      if (widget) {
        bodyEl.appendChild(widget.element);
        if (widget.binding) {
          widgetBindings.push(widget.binding);
        }
        if (widget.control) {
          controlElements.add(widget.control);
        }
      }
    });

    scadaContainer.appendChild(node);
  });

  renderView(currentView);
  applyScopedTopics();
  updateRoleUI();
}

function buildWidget(definition, containerIndex, objectIndex) {
  const { type, topic, label, unit, min, max, color, onColor, offColor, payload } = definition;
  const widgetId = `c${containerIndex}-o${objectIndex}`;
  const relTopic = topic || "";
  const normalizedTopic = normalizeRelativePath(relTopic);
  const binding = {
    topic: normalizedTopic,
    update: () => {}
  };

  switch ((type || "").toLowerCase()) {
    case "level": {
      const widget = createLevelIndicator(`${widgetId}-level`, label, unit || "%", color || "#3a86ff");
      binding.update = widget.update;
      return { element: widget.element, binding };
    }
    case "pumpstatus": {
      const widget = createPumpStatus(`${widgetId}-pump`, label || "Estado", onColor || "#00ff9d", offColor || "#6c757d");
      binding.update = widget.update;
      return { element: widget.element, binding };
    }
    case "gauge": {
      const widget = createGauge(`${widgetId}-gauge`, label || "Indicador", unit || "", min ?? 0, max ?? 100, color || "#00b4d8");
      binding.update = widget.update;
      return { element: widget.element, binding };
    }
    case "number": {
      const widget = createNumberIndicator(`${widgetId}-number`, label || "Valor", unit || "");
      binding.update = widget.update;
      return { element: widget.element, binding };
    }
    case "text": {
      const widget = createTextIndicator(`${widgetId}-text`, label || "Texto");
      binding.update = widget.update;
      return { element: widget.element, binding };
    }
    case "motorspeed": {
      const widget = createMotorSpeed(`${widgetId}-speed`, label || "Velocidad", unit || "rpm");
      binding.update = widget.update;
      return { element: widget.element, binding };
    }
    case "startbtn":
    case "stopbtn":
    case "resetbtn": {
      const btn = createControlButton(type, label, color, normalizedTopic, payload ?? type);
      return { element: btn, control: btn };
    }
    default:
      console.warn("Tipo de widget no soportado:", type);
      return null;
  }
}

function createControlButton(kind, label, color, topic, payload) {
  const button = document.createElement("button");
  button.className = `btn control-button btn-${kind.toLowerCase()}`;
  button.textContent = label || kind;
  if (color) {
    button.style.background = color;
  }
  button.addEventListener("click", () => {
    if (currentRole === "viewer" || currentRole === "visualizacion") {
      appendLog("Acción bloqueada: rol sin permisos de control");
      return;
    }
    publishRelative(topic, payload ?? kind);
  });
  return button;
}

function createLevelIndicator(id, label, unit, color) {
  const container = document.createElement("div");
  container.className = "tank-container";
  const level = document.createElement("div");
  level.id = id;
  level.className = "tank-level";
  if (color) level.style.background = color;
  const indicator = document.createElement("p");
  indicator.className = "level-indicator";
  indicator.innerHTML = `<span>${label || "Nivel"}:</span> <span id="${id}-value" class="value">0</span> ${unit}`;
  container.append(level, indicator);
  return {
    element: container,
    update: (value) => {
      const numeric = parseFloat(value);
      if (Number.isFinite(numeric)) {
        const pct = Math.max(0, Math.min(100, numeric));
        document.getElementById(id).style.height = `${pct}%`;
        document.getElementById(`${id}-value`).textContent = pct.toFixed(1);
      }
    }
  };
}

function createPumpStatus(id, label, onColor, offColor) {
  const wrapper = document.createElement("div");
  wrapper.className = "pump-status";
  const indicator = document.createElement("span");
  indicator.id = id;
  indicator.className = "pump-indicator";
  const text = document.createElement("span");
  text.id = `${id}-state`;
  text.textContent = label || "Estado";
  wrapper.append(indicator, text);
  return {
    element: wrapper,
    update: (value) => {
      const strValue = String(value ?? "").toLowerCase();
      const isOn = strValue === "on" || strValue === "1" || strValue === "true";
      indicator.style.backgroundColor = isOn ? onColor : offColor;
      text.textContent = `${label || "Estado"} ${isOn ? "ON" : "OFF"}`;
    }
  };
}

function createGauge(id, label, unit, min, max, color) {
  const wrapper = document.createElement("div");
  wrapper.className = "gauge-container";
  const dial = document.createElement("div");
  dial.className = "gauge-dial";
  const fill = document.createElement("div");
  fill.id = id;
  fill.className = "gauge-fill";
  if (color) {
    fill.style.background = color;
  }
  dial.appendChild(fill);
  const center = document.createElement("div");
  center.className = "gauge-center";
  const labelEl = document.createElement("div");
  labelEl.className = "gauge-label";
  labelEl.textContent = `${label || "Indicador"} (${unit || ""})`;
  const valueEl = document.createElement("div");
  valueEl.id = `${id}-value`;
  valueEl.className = "gauge-value";
  valueEl.textContent = "0";
  wrapper.append(dial, center, labelEl, valueEl);
  return {
    element: wrapper,
    update: (value) => {
      const numeric = parseFloat(value);
      if (!Number.isFinite(numeric)) return;
      const clamped = Math.max(min ?? numeric, Math.min(max ?? numeric, numeric));
      const angle = ((clamped - (min ?? 0)) / ((max ?? 100) - (min ?? 0))) * 180 - 90;
      document.getElementById(id).style.transform = `rotate(${angle}deg)`;
      document.getElementById(`${id}-value`).textContent = numeric.toFixed(1);
    }
  };
}

function createNumberIndicator(id, label, unit) {
  const wrapper = document.createElement("div");
  wrapper.className = "number-indicator";
  wrapper.innerHTML = `<span>${label}:</span> <span id="${id}" class="value">0</span> ${unit}`;
  return {
    element: wrapper,
    update: (value) => {
      const numeric = parseFloat(value);
      document.getElementById(id).textContent = Number.isFinite(numeric) ? numeric.toFixed(2) : value;
    }
  };
}

function createTextIndicator(id, label) {
  const wrapper = document.createElement("div");
  wrapper.className = "text-indicator";
  wrapper.innerHTML = `<span>${label}:</span> <span id="${id}" class="value"></span>`;
  return {
    element: wrapper,
    update: (value) => {
      document.getElementById(id).textContent = value ?? "";
    }
  };
}

function createMotorSpeed(id, label, unit) {
  const wrapper = document.createElement("div");
  wrapper.className = "motor-speed";
  wrapper.innerHTML = `<span>${label}:</span> <span id="${id}">0</span> ${unit}`;
  return {
    element: wrapper,
    update: (value) => {
      const numeric = parseFloat(value);
      document.getElementById(id).textContent = Number.isFinite(numeric) ? numeric.toFixed(1) : value;
    }
  };
}

function renderView(view) {
  currentView = view;
  scadaContainer.classList.toggle("matrix-view", view === "matrix");
  scadaContainer.classList.toggle("sidebar-view", view === "sidebar");
  viewMatrixBtn.classList.toggle("active", view === "matrix");
  viewSidebarBtn.classList.toggle("active", view === "sidebar");
}

function handleViewToggle() {
  viewMatrixBtn?.addEventListener("click", () => renderView("matrix"));
  viewSidebarBtn?.addEventListener("click", () => renderView("sidebar"));
}

function setupLoginDialog() {
  openLoginBtn?.addEventListener("click", () => {
    if (!firebase.auth().currentUser) {
      loginDialog.showModal();
    }
  });
  closeLoginBtn?.addEventListener("click", () => {
    loginDialog.close();
    loginForm.reset();
  });
}

function publishRelative(relativePath, payload, qos = 0, retain = false) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    appendLog("No se puede publicar: WS cerrado");
    return;
  }
  if (!uid) {
    appendLog("No se puede publicar: UID no definido");
    return;
  }
  const topic = `scada/customers/${uid}/${normalizeRelativePath(relativePath)}`;
  const message = { type: "publish", topic, payload, qos, retain };
  ws.send(JSON.stringify(message));
  appendLog(`TX ${topic} ${JSON.stringify(payload)}`);
}

function publishAbsolute(topic, payload, qos = 0, retain = false) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    appendLog("No se puede publicar: WS cerrado");
    return;
  }
  const message = { type: "publish", topic, payload, qos, retain };
  ws.send(JSON.stringify(message));
  appendLog(`TX ${topic} ${JSON.stringify(payload)}`);
}

window.publishRelative = publishRelative;
window.publishAbsolute = publishAbsolute;

function hydrateDashboard(email) {
  loadScadaConfig()
    .then((config) => {
      scadaConfig = config;
      if (config.mainTitle) {
        document.getElementById("main-title").textContent = config.mainTitle;
      }
      currentRole = determineRole(email) || "operador";
      clearDashboard();
      renderDashboard();
    })
    .catch((error) => {
      console.error("Error cargando configuración", error);
      scadaContainer.innerHTML = `<p>Error cargando configuración: ${error.message}</p>`;
    });
}

function resetSessionState() {
  currentRole = "viewer";
  uid = null;
  clearDashboard();
  scadaContainer.innerHTML = '<p class="empty-state">Inicia sesion para cargar tu tablero SCADA.</p>';
  if (sidebarMenu) {
    sidebarMenu.hidden = true;
  }
  updateConnectionChip(false);
  setCurrentUser();
  updateRoleUI();
  if (configLink) {
    configLink.hidden = true;
  }
}

handleViewToggle();
setupLoginDialog();

if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = emailInput.value.trim();
    const password = passwordInput.value;
    if (!email || !password) {
      setStatus("Email y password requeridos");
      return;
    }
    try {
      await login(email, password);
      loginDialog.close();
      loginForm.reset();
    } catch (error) {
      setStatus(error.message);
      appendLog(`Login fallido: ${error.message}`);
    }
  });
}

if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    clearTimeout(reconnectTimer);
    lastToken = null;
    disconnectWs("logout");
    await firebase.auth().signOut();
  });
}

firebase.auth().onAuthStateChanged(async (user) => {
  clearTimeout(reconnectTimer);
  if (user) {
    setCurrentUser(user.email);
    setStatus(`Sesión activa: ${user.email}`);
    logoutBtn?.removeAttribute("disabled");
    openLoginBtn?.setAttribute("disabled", "");
    hydrateDashboard(user.email);
    await connectWs(user);
  } else {
    setStatus("Sin sesión");
    logoutBtn?.setAttribute("disabled", "");
    openLoginBtn?.removeAttribute("disabled");
    resetSessionState();
  }
});

firebase.auth().onIdTokenChanged(async (user) => {
  if (user) {
    await connectWs(user);
  }
});
