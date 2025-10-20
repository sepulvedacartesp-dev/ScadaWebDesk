const BACKEND_HTTP = "https://scadawebdesk.onrender.com";
const BACKEND_WS = "wss://scadawebdesk.onrender.com/ws";
const DEFAULT_MAIN_TITLE = "SCADA Web Desk";

let ws = null;
let uid = null;
let reconnectTimer = null;
let lastToken = null;
let scadaConfig = null;
let currentCompanyId = null;
let currentRole = "viewer";
let currentView = "matrix";

const loginForm = document.getElementById("login-form");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const statusLabel = document.getElementById("status");
const logoutBtn = document.getElementById("logout-btn");
const openLoginBtn = document.getElementById("open-login");
const closeLoginBtn = document.getElementById("close-login");
const loginDialog = document.getElementById("login-dialog");
const connectChip = document.getElementById("connect-status");
const configLink = document.getElementById("config-link");
const currentUserLabel = document.getElementById("current-user");
const currentCompanyLabel = document.getElementById("current-company");
const brandGroup = document.getElementById("brand-group");
const brandLogoImg = document.getElementById("company-logo");
const brandLogoFallback = document.querySelector(".brand-logo");
const mainTitleNode = document.getElementById("main-title");
const scadaContainer = document.getElementById("scada-container");
const viewMatrixBtn = document.getElementById("view-matrix");
const viewSidebarBtn = document.getElementById("view-sidebar");
const sidebarMenu = document.getElementById("sidebar-menu");


const topicElementMap = new Map();
const topicStateCache = new Map();
const controlElements = new Set();
const widgetBindings = [];
const containerNodes = [];
const sidebarButtons = [];
let selectedContainerIndex = 0;
let currentLogoEmpresa = null;
let currentLogoVersion = 0;

function setStatus(text) {
  if (statusLabel) {
    statusLabel.textContent = text;
  }
}

function computeBrandInitials(value) {
  if (!value) return "SW";
  const tokens = String(value)
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!tokens.length) return "SW";
  const initials = tokens
    .slice(0, 2)
    .map((word) => (word && word[0] ? word[0].toUpperCase() : ""))
    .join("");
  return initials || "SW";
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
  currentLogoEmpresa = null;
  currentLogoVersion = 0;
}

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
  brandLogoImg.alt = `Logo de ${resolvedTitle}`;
  brandLogoImg.src = url;
}


function normalizeRelativePath(relPath) {
  return relPath.split("/").filter(Boolean).join("/");
}

function scopedTopic(relative) {
  const empresa = currentCompanyId || scadaConfig?.empresaId || null;
  if (!empresa) return null;
  const base = `scada/customers/${empresa}`;
  return `${base}/${normalizeRelativePath(relative)}`;
}

async function login(email, password) {
  setStatus("Iniciando sesiÃ³n...");
  await firebase.auth().signInWithEmailAndPassword(email, password);
  setStatus("SesiÃ³n iniciada, conectando...");
}

function disconnectWs(reason) {
  if (ws) {
    ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
    try { ws.close(); } catch (_) { /* ignore */ }
  }
  ws = null;
  updateConnectionChip(false);
  if (reason) {
    console.info(`WS cerrado (${reason})`);
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
      console.info("WS abierto");
      updateConnectionChip(true);
      setStatus(`Conectado como ${user.email}`);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "hello") {
          handleHello(msg);
        } else if (msg.type === "ack") {
          console.debug(`ACK ${msg.topic}`);
        } else if (msg.type === "error") {
          console.error(`ERROR ${msg.error}`);
        } else if (msg.topic) {
          handleTopicMessage(msg);
        }
      } catch (err) {
        console.error(`Mensaje WS invÃ¡lido: ${err}`);
      }
    };

    ws.onclose = (event) => {
      console.warn(`WS cerrado codigo=${event.code}`);
      ws = null;
      updateConnectionChip(false);
      if (firebase.auth().currentUser) {
        scheduleReconnect();
      } else {
        setStatus("SesiÃ³n cerrada");
      }
    };

    ws.onerror = (err) => {
      console.error(`WS error ${err.message || err}`);
    };
  } catch (error) {
    console.error(`No se pudo abrir WS: ${error.message || error}`);
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
  if (msg.empresaId) {
    currentCompanyId = msg.empresaId;
  }
  console.debug(`HELLO uid=${uid} empresa=${currentCompanyId || ""}`);
  const helloCompany = msg.empresaId || null;
  if (helloCompany && scadaConfig && scadaConfig.empresaId && scadaConfig.empresaId !== helloCompany) {
    const user = firebase.auth().currentUser;
    if (user) {
      hydrateDashboard(user, { forceRefresh: true }).catch((err) => {
        console.error("No se pudo actualizar configuración tras handshake", err);
      });
    }
  }
  if (Array.isArray(msg.last_values)) {
    msg.last_values.forEach((entry) => {
      if (entry && entry.topic) {
        handleTopicMessage({ topic: entry.topic, payload: entry.payload });
      }
    });
  }
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

function setCurrentUser(email, empresaId) {
  if (currentUserLabel) {
    currentUserLabel.textContent = email || 'Anonimo';
  }
  if (currentCompanyLabel) {
    if (empresaId) {
      currentCompanyLabel.hidden = false;
      currentCompanyLabel.textContent = `Empresa: ${empresaId}`;
    } else {
      currentCompanyLabel.hidden = true;
      currentCompanyLabel.textContent = '';
    }
  }
}



function determineRole(email) {
  if (!scadaConfig || !email) return "operador";
  const roles = scadaConfig.roles || {};
  if (Array.isArray(roles.admins) && roles.admins.includes(email)) return "admin";
  if (Array.isArray(roles.operators) && roles.operators.includes(email)) return "operador";
  if (Array.isArray(roles.viewers) && roles.viewers.includes(email)) return "visualizacion";
  return "operador";
}

async function fetchScadaConfig(user, forceRefresh = false) {
  if (!user) {
    throw new Error("Usuario no autenticado");
  }
  if (!forceRefresh && scadaConfig && currentCompanyId) {
    return { config: scadaConfig, role: currentRole, empresaId: currentCompanyId };
  }
  const idToken = await user.getIdToken(forceRefresh);
  const response = await fetch(BACKEND_HTTP + "/config", {
    headers: {
      Authorization: "Bearer " + idToken,
    },
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `No se pudo cargar configuración (${response.status})`);
  }
  const payload = await response.json();
  scadaConfig = payload.config || {};
  currentCompanyId = payload.empresaId || scadaConfig.empresaId || null;
  scadaConfig.empresaId = currentCompanyId;
  const email = user.email || "";
  currentRole = payload.role || determineRole(email) || "operador";
  return { config: scadaConfig, role: currentRole, empresaId: currentCompanyId };
}
function clearDashboard() {
  widgetBindings.length = 0;
  controlElements.clear();
  topicElementMap.clear();
  containerNodes.length = 0;
  sidebarButtons.length = 0;
  selectedContainerIndex = 0;
  scadaContainer.innerHTML = "";
  if (sidebarMenu) {
    sidebarMenu.innerHTML = "";
    sidebarMenu.hidden = true;
  }
}

function renderDashboard() {
  if (!scadaConfig || !Array.isArray(scadaConfig.containers)) {
    scadaContainer.innerHTML = "<p>No hay configuraciÃ³n disponible.</p>";
    return;
  }

  const template = document.getElementById("container-template");
  scadaContainer.classList.toggle("sidebar-view", currentView === "sidebar");
  scadaConfig.containers.forEach((container, index) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const titleEl = node.querySelector(".container-title");
    const bodyEl = node.querySelector(".container-body");
    if (titleEl) titleEl.textContent = container.title || `Contenedor ${index + 1}`;

    if (sidebarMenu) {
      const navButton = document.createElement("button");
      navButton.type = "button";
      navButton.className = "sidebar-nav-btn";
      navButton.textContent = container.title || `Contenedor ${index + 1}`;
      navButton.addEventListener("click", () => {
        selectContainer(index);
        if (currentView === "matrix") {
          node.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
      sidebarButtons.push(navButton);
      sidebarMenu.appendChild(navButton);
    }

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

    containerNodes.push(node);
    scadaContainer.appendChild(node);
  });

  if (containerNodes.length) {
    selectContainer(Math.min(selectedContainerIndex, containerNodes.length - 1));
  } else if (sidebarMenu) {
    sidebarMenu.hidden = true;
  }

  renderView(currentView);
  applyScopedTopics();
  updateRoleUI();
}

function selectContainer(index) {
  if (!containerNodes.length) return;
  const clamped = Math.max(0, Math.min(index, containerNodes.length - 1));
  selectedContainerIndex = clamped;
  updateSidebarMenuState();
  updateSidebarVisibility();
}

function updateSidebarMenuState() {
  sidebarButtons.forEach((btn, idx) => {
    btn.classList.toggle("active", idx === selectedContainerIndex);
  });
}

function updateSidebarVisibility() {
  const isSidebar = currentView === "sidebar";
  const trackedNodes = containerNodes.length ? containerNodes : Array.from(scadaContainer.querySelectorAll(".container-card"));
  if (!trackedNodes.length) {
    const fallbackNodes = Array.from(scadaContainer.querySelectorAll(".container-card"));
    fallbackNodes.forEach((node) => {
      if (isSidebar) {
        node.classList.remove("sidebar-active");
        node.setAttribute("hidden", "");
        node.style.display = "none";
        node.setAttribute("aria-hidden", "true");
      } else {
        node.classList.remove("sidebar-active");
        node.removeAttribute("hidden");
        node.style.display = "";
        node.removeAttribute("aria-hidden");
      }
    });
    return;
  }

  const activeIndex = Math.max(0, Math.min(selectedContainerIndex, trackedNodes.length - 1));
  selectedContainerIndex = activeIndex;

  trackedNodes.forEach((node, idx) => {
    const isActive = isSidebar && idx === activeIndex;
    if (isSidebar) {
      node.classList.toggle("sidebar-active", isActive);
      if (isActive) {
        node.removeAttribute("hidden");
        node.style.display = "";
        node.removeAttribute("aria-hidden");
      } else {
        node.setAttribute("hidden", "");
        node.style.display = "none";
        node.setAttribute("aria-hidden", "true");
      }
    } else {
      node.classList.remove("sidebar-active");
      node.removeAttribute("hidden");
      node.style.display = "";
      node.removeAttribute("aria-hidden");
    }
  });

  const extras = Array.from(scadaContainer.querySelectorAll(".container-card")).filter((node) => !trackedNodes.includes(node));
  extras.forEach((node) => {
    if (isSidebar) {
      node.classList.remove("sidebar-active");
      node.setAttribute("hidden", "");
      node.style.display = "none";
      node.setAttribute("aria-hidden", "true");
    } else {
      node.classList.remove("sidebar-active");
      node.removeAttribute("hidden");
      node.style.display = "";
      node.removeAttribute("aria-hidden");
    }
  });
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
      const widget = createLevelIndicator(`${widgetId}-level`, label, unit || "%", color || "#3a86ff", min ?? 0, max ?? 100);
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
      console.warn("AcciÃ³n bloqueada: rol sin permisos de control");
      return;
    }
    publishRelative(topic, payload ?? kind);
  });
  return button;
}

function createLevelIndicator(id, label, unit, color, min, max) {
  const container = document.createElement("div");
  container.className = "tank-container";
  const level = document.createElement("div");
  level.id = id;
  level.className = "tank-level";
  if (color) level.style.background = color;
  const indicator = document.createElement("p");
  indicator.className = "level-indicator";
  const labelSpan = document.createElement("span");
  labelSpan.textContent = `${label || "Nivel"}:`;
  const valueSpan = document.createElement("span");
  valueSpan.id = `${id}-value`;
  valueSpan.className = "value";
  valueSpan.textContent = "0";
  indicator.append(labelSpan, document.createTextNode(" "), valueSpan);
  if (unit) {
    indicator.append(document.createTextNode(` ${unit}`));
  }
  container.append(level, indicator);

  const minValue = Number.isFinite(min) ? min : 0;
  let maxValue;
  if (Number.isFinite(max)) {
    maxValue = max;
  } else if (Number.isFinite(min)) {
    maxValue = minValue + 100;
  } else {
    maxValue = 100;
  }
  if (maxValue <= minValue) {
    maxValue = minValue + 1;
  }
  const span = maxValue - minValue;

  return {
    element: container,
    update: (value) => {
      const numeric = parseFloat(value);
      if (!Number.isFinite(numeric)) return;
      const clamped = Math.min(Math.max(numeric, minValue), maxValue);
      const pct = span === 0 ? 0 : ((clamped - minValue) / span) * 100;
      level.style.height = `${pct}%`;
      valueSpan.textContent = numeric.toFixed(1);
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
  if (color) {
    wrapper.style.setProperty('--gauge-accent', color);
  }
  const dial = document.createElement("div");
  dial.className = "gauge-dial";

  const ticksFragment = document.createDocumentFragment();
  const tickSteps = 10;
  for (let i = 0; i <= tickSteps; i += 1) {
    const tick = document.createElement('span');
    tick.className = 'gauge-tick';
    if (i % 5 === 0) {
      tick.classList.add('is-major');
    }
    const rotation = -90 + (i / tickSteps) * 180;
    tick.style.transform = `rotate(${rotation}deg) translateY(-6%)`;
    ticksFragment.appendChild(tick);
  }
  dial.appendChild(ticksFragment);

  const needle = document.createElement('div');
  needle.id = id;
  needle.className = 'gauge-needle';
  dial.appendChild(needle);

  const center = document.createElement('div');
  center.className = 'gauge-center';
  dial.appendChild(center);

  const minValue = Number.isFinite(min) ? min : 0;
  let maxValue;
  if (Number.isFinite(max)) {
    maxValue = max;
  } else if (Number.isFinite(min)) {
    maxValue = minValue + 100;
  } else {
    maxValue = 100;
  }
  if (maxValue <= minValue) {
    maxValue = minValue + 1;
  }
  const span = maxValue - minValue;

  const formatValue = (num, digits = 1) => {
    if (!Number.isFinite(num)) return '--';
    return Number.isInteger(num) ? num.toString() : num.toFixed(digits);
  };

  const scale = document.createElement('div');
  scale.className = 'gauge-scale';
  const minLabel = document.createElement('span');
  minLabel.textContent = formatValue(minValue);
  const maxLabel = document.createElement('span');
  maxLabel.textContent = formatValue(maxValue);
  scale.append(minLabel, maxLabel);

  const info = document.createElement('div');
  info.className = 'gauge-info';
  const labelEl = document.createElement('div');
  labelEl.className = 'gauge-label';
  labelEl.textContent = label || 'Indicador';
  const reading = document.createElement('div');
  reading.className = 'gauge-reading';
  const valueEl = document.createElement('span');
  valueEl.id = `${id}-value`;
  valueEl.className = 'gauge-value';
  valueEl.textContent = '0';
  const unitEl = document.createElement('span');
  unitEl.className = 'gauge-unit';
  const unitText = unit ? String(unit).trim() : '';
  if (unitText) {
    unitEl.textContent = unitText;
  } else {
    unitEl.classList.add('is-hidden');
  }
  reading.append(valueEl, unitEl);
  info.append(labelEl, reading);

  wrapper.append(dial, scale, info);

  return {
    element: wrapper,
    update: (value) => {
      const numeric = parseFloat(value);
      if (!Number.isFinite(numeric)) return;
      const clamped = Math.min(Math.max(numeric, minValue), maxValue);
      const ratio = span === 0 ? 0 : (clamped - minValue) / span;
      const angle = ratio * 180 - 90;
      needle.style.transform = `rotate(${angle}deg)`;
      valueEl.textContent = formatValue(clamped);
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
  if (sidebarMenu) {
    sidebarMenu.hidden = view !== "sidebar" || containerNodes.length === 0;
  }
  if (view === "sidebar") {
    if (containerNodes.length) {
      selectContainer(selectedContainerIndex);
    } else {
      updateSidebarMenuState();
      updateSidebarVisibility();
    }
  } else {
    updateSidebarMenuState();
    updateSidebarVisibility();
  }
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
    console.warn("No se puede publicar: WS cerrado");
    return;
  }
  const topic = scopedTopic(relativePath);
  if (!topic) {
    console.warn("No se pudo publicar: empresa no definida");
    return;
  }
  const message = { type: "publish", topic, payload, qos, retain };
  ws.send(JSON.stringify(message));
  console.debug(`TX ${topic} ${JSON.stringify(payload)}`);
}

function publishAbsolute(topic, payload, qos = 0, retain = false) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn("No se puede publicar: WS cerrado");
    return;
  }
  const message = { type: "publish", topic, payload, qos, retain };
  ws.send(JSON.stringify(message));
  console.debug(`TX ${topic} ${JSON.stringify(payload)}`);
}

window.publishRelative = publishRelative;
window.publishAbsolute = publishAbsolute;

async function hydrateDashboard(user, { forceRefresh = false } = {}) {
  if (!user) {
    return;
  }
  try {
    const { config, role, empresaId } = await fetchScadaConfig(user, forceRefresh);
    const resolvedTitle = (config.mainTitle || DEFAULT_MAIN_TITLE).trim() || DEFAULT_MAIN_TITLE;
    if (mainTitleNode) {
      mainTitleNode.textContent = resolvedTitle;
    }
    document.title = resolvedTitle;
    currentRole = role || "operador";
    clearDashboard();
    renderDashboard();
    const resolvedEmpresa = empresaId || currentCompanyId;
    updateBrandLogo(resolvedEmpresa, { forceRefresh, title: resolvedTitle });
    setCurrentUser(user.email, resolvedEmpresa);
    if (resolvedEmpresa) {
      setStatus(`Tablero cargado (${resolvedEmpresa})`);
    } else {
      setStatus("Tablero cargado");
    }
  } catch (error) {
    console.error("Error cargando configuración", error);
    scadaContainer.innerHTML = `<p>Error cargando configuración: ${error.message}</p>`;
  }
}

function resetSessionState() {
  scadaConfig = null;
  currentCompanyId = null;
  currentRole = "viewer";
  uid = null;
  clearDashboard();
  scadaContainer.innerHTML = '<p class="empty-state">Inicia sesion para cargar tu tablero SCADA.</p>';
  if (sidebarMenu) {
    sidebarMenu.hidden = true;
  }
  if (mainTitleNode) {
    mainTitleNode.textContent = DEFAULT_MAIN_TITLE;
  }
  document.title = DEFAULT_MAIN_TITLE;
  clearBrandLogo(DEFAULT_MAIN_TITLE);
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
      console.error(`Login fallido: ${error.message}`);
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
    setStatus(`SesiÃ³n activa: ${user.email}`);
    logoutBtn?.removeAttribute("disabled");
    openLoginBtn?.setAttribute("disabled", "");
    await hydrateDashboard(user);
    await connectWs(user);
  } else {
    setStatus("Sin sesiÃ³n");
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













