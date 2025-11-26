const BACKEND_HTTP = "https://scadawebdesk.onrender.com";
const BACKEND_WS = "wss://scadawebdesk.onrender.com/ws";
const DEFAULT_MAIN_TITLE = "SurNex SCADA Web";
const MAIN_TITLE_STORAGE_KEY = "scada-main-title";
const PLANT_SELECTION_STORAGE_KEY = "scada-plant-selection";

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
const trendLink = document.getElementById("trend-link");
const cotizadorLink = document.getElementById("cotizador-link");
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
const currentPlantLabel = document.getElementById("current-plant");
const plantSelectorSection = document.getElementById("plant-selector");
const plantSelect = document.getElementById("plant-select");
const plantEmptyMessage = document.getElementById("plant-empty");


const topicElementMap = new Map();
const topicStateCache = new Map();
const controlElements = new Set();
const widgetBindings = [];
const containerNodes = [];
const normalContainerNodes = [];
const generalContainerNodes = [];
const sidebarButtons = [];
let selectedContainerIndex = 0;
let currentLogoEmpresa = null;
let currentLogoVersion = 0;
let canAccessCotizador = false;
let availablePlants = [];
let accessiblePlantIds = [];
let selectedPlantId = null;

function persistMainTitle(value) {
  const nextTitle = (value || "").trim() || DEFAULT_MAIN_TITLE;
  try {
    sessionStorage.setItem(MAIN_TITLE_STORAGE_KEY, nextTitle);
  } catch (_) {
    /* ignore storage errors */
  }
  try {
    localStorage.setItem(MAIN_TITLE_STORAGE_KEY, nextTitle);
  } catch (_) {
    /* ignore storage errors */
  }
  return nextTitle;
}

function clearStoredMainTitle() {
  try {
    sessionStorage.removeItem(MAIN_TITLE_STORAGE_KEY);
  } catch (_) {
    /* ignore storage errors */
  }
  try {
    localStorage.removeItem(MAIN_TITLE_STORAGE_KEY);
  } catch (_) {
    /* ignore storage errors */
  }
}

function normalizePlant(raw) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const id = typeof raw.id === "string" ? raw.id.trim().toLowerCase() : "";
  if (!id) {
    return null;
  }
  return {
    id,
    name: typeof raw.name === "string" && raw.name.trim() ? raw.name.trim() : id,
    serialCode: typeof raw.serialCode === "string" ? raw.serialCode.trim() : "",
    description: typeof raw.description === "string" ? raw.description : "",
    active: raw.active !== false,
  };
}

function plantStorageKey(companyId) {
  return `${PLANT_SELECTION_STORAGE_KEY}-${companyId || "default"}`;
}

function persistPlantSelection(companyId, plantId) {
  if (!companyId || !plantId) return;
  const normalizedId = plantId.toLowerCase();
  try {
    localStorage.setItem(plantStorageKey(companyId), normalizedId);
  } catch (_) {
    /* ignore storage issues */
  }
}

function loadStoredPlant(companyId) {
  if (!companyId) return null;
  try {
    return localStorage.getItem(plantStorageKey(companyId));
  } catch (_) {
    return null;
  }
}

function setAvailablePlants(plants, allowedIds, empresaId) {
  const normalizedPlants = Array.isArray(plants)
    ? plants.map((item) => normalizePlant(item)).filter(Boolean)
    : [];
  let allowedList = Array.isArray(allowedIds) ? allowedIds.map((item) => String(item).toLowerCase()) : [];
  if (!allowedList.length) {
    allowedList = normalizedPlants.map((plant) => plant.id);
  }
  availablePlants = normalizedPlants.filter((plant) => allowedList.includes(plant.id));
  accessiblePlantIds = availablePlants.map((plant) => plant.id);
  const stored = loadStoredPlant(empresaId);
  const normalizedStored = typeof stored === "string" ? stored.toLowerCase() : null;
  if (normalizedStored && accessiblePlantIds.includes(normalizedStored)) {
    selectedPlantId = normalizedStored;
  } else if (!selectedPlantId || !accessiblePlantIds.includes(selectedPlantId)) {
    selectedPlantId = accessiblePlantIds[0] || null;
  }
  if (selectedPlantId) {
    persistPlantSelection(empresaId, selectedPlantId);
  }
  updatePlantSelectorUI();
  updatePlantBadge();
}

function getCurrentPlant() {
  if (!selectedPlantId) return availablePlants[0] || null;
  return availablePlants.find((plant) => plant.id === selectedPlantId) || availablePlants[0] || null;
}

function updatePlantSelectorUI() {
  if (!plantSelect) return;
  plantSelect.innerHTML = "";
  if (!accessiblePlantIds.length) {
    if (plantSelectorSection) plantSelectorSection.hidden = true;
    if (plantEmptyMessage) plantEmptyMessage.hidden = false;
    return;
  }
  if (plantSelectorSection) plantSelectorSection.hidden = false;
  if (plantEmptyMessage) plantEmptyMessage.hidden = true;
  availablePlants.forEach((plant) => {
    const option = document.createElement("option");
    option.value = plant.id;
    option.textContent = plant.name || plant.id;
    option.selected = plant.id === selectedPlantId;
    plantSelect.appendChild(option);
  });
  plantSelect.disabled = accessiblePlantIds.length <= 1;
}

function updatePlantBadge() {
  if (!currentPlantLabel) return;
  const plant = getCurrentPlant();
  if (plant) {
    currentPlantLabel.hidden = false;
    currentPlantLabel.textContent = `Planta: ${plant.name}`;
  } else {
    currentPlantLabel.hidden = true;
    currentPlantLabel.textContent = "";
  }
}

function handlePlantChange(event) {
  const nextId = event?.target?.value || null;
  if (!nextId || nextId === selectedPlantId) {
    return;
  }
  const normalizedId = nextId.toLowerCase();
  if (!accessiblePlantIds.includes(normalizedId)) {
    return;
  }
  selectedPlantId = normalizedId;
  persistPlantSelection(currentCompanyId, selectedPlantId);
  clearDashboard();
  renderDashboard();
  applyScopedTopics();
  updatePlantBadge();
}

function getVisibleContainers() {
  if (!scadaConfig || !Array.isArray(scadaConfig.containers)) {
    return [];
  }
  if (!selectedPlantId) {
    return scadaConfig.containers.slice();
  }
  return scadaConfig.containers.filter((container) => {
    const plantId = typeof container?.plantId === "string" ? container.plantId.trim().toLowerCase() : "";
    return plantId ? plantId === selectedPlantId : false;
  });
}

function isGeneralContainer(container) {
  return !!(container && container.isGeneral);
}

function orderContainersForView(containers) {
  if (!Array.isArray(containers)) return { ordered: [], normal: [] };
  const generalList = [];
  const normalList = [];
  containers.forEach((container) => {
    if (isGeneralContainer(container) && !generalList.length) {
      generalList.push(container);
    } else {
      normalList.push(container);
    }
  });
  const ordered = generalList.length ? [...generalList, ...normalList] : normalList;
  return { ordered, normal: normalList };
}

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
  const plant = getCurrentPlant();
  if (!empresa || !plant || !plant.serialCode) return null;
  const base = `scada/customers/${empresa}/${plant.serialCode}`;
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
  if (trendLink) {
    trendLink.hidden = true;
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
  if (cotizadorLink) {
    cotizadorLink.hidden = !canAccessCotizador;
  }
  controlElements.forEach((btn) => {
    const isLocked = btn?.dataset?.locked === "true";
    if (isViewer) {
      btn.setAttribute("disabled", "");
      btn.classList.add("control-disabled");
    } else {
      if (isLocked) {
        btn.setAttribute("disabled", "");
        btn.classList.add("control-disabled");
      } else {
        btn.removeAttribute("disabled");
        btn.classList.remove("control-disabled");
      }
    }
  });
}

function setCurrentUser(email, empresaId) {
  if (currentUserLabel) {
    currentUserLabel.textContent = email || 'Anonimo';
  }
  if (trendLink) {
    trendLink.hidden = !email;
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
  updatePlantBadge();
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
    return { config: scadaConfig, role: currentRole, empresaId: currentCompanyId, canAccessCotizador };
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
  canAccessCotizador = Boolean(payload.canAccessCotizador);
  const plants = Array.isArray(payload.plants) ? payload.plants : (scadaConfig.plants || []);
  const accessible = Array.isArray(payload.accessiblePlants) ? payload.accessiblePlants : [];
  return {
    config: scadaConfig,
    role: currentRole,
    empresaId: currentCompanyId,
    canAccessCotizador,
    plants,
    accessiblePlants: accessible,
  };
}
function clearDashboard() {
  widgetBindings.length = 0;
  controlElements.clear();
  topicElementMap.clear();
  generalContainerNodes.forEach((node) => {
    if (node && node.remove) {
      node.remove();
    }
  });
  containerNodes.length = 0;
  normalContainerNodes.length = 0;
  generalContainerNodes.length = 0;
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
    scadaContainer.innerHTML = "<p>No hay configuracion disponible.</p>";
    if (sidebarMenu) sidebarMenu.hidden = true;
    return;
  }
  const visibleContainers = getVisibleContainers();
  containerNodes.length = 0;
  normalContainerNodes.length = 0;
  generalContainerNodes.length = 0;
  sidebarButtons.length = 0;
  scadaContainer.innerHTML = "";
  const scadaGrid = scadaContainer?.parentElement;
  if (sidebarMenu) {
    sidebarMenu.innerHTML = "";
  }
  if (!visibleContainers.length) {
    scadaContainer.innerHTML = "<p>No hay contenedores para la planta seleccionada.</p>";
    if (sidebarMenu) sidebarMenu.hidden = true;
    return;
  }

  const { ordered } = orderContainersForView(visibleContainers);
  const template = document.getElementById("container-template");
  scadaContainer.classList.toggle("sidebar-view", currentView === "sidebar");
  let generalAssigned = false;
  ordered.forEach((container, index) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const titleEl = node.querySelector(".container-title");
    const bodyEl = node.querySelector(".container-body");
    const isGeneral = isGeneralContainer(container) && !generalAssigned;
    if (isGeneral) {
      generalAssigned = true;
    }
    if (titleEl) titleEl.textContent = container.title || `Contenedor ${index + 1}`;
    const plantBadge = node.querySelector(".container-plant");
    if (plantBadge) {
      const plant = getCurrentPlant();
      if (plant) {
        plantBadge.hidden = false;
        plantBadge.textContent = plant.name;
      } else {
        plantBadge.hidden = true;
      }
    }

    node.dataset.isGeneral = isGeneral ? "true" : "false";
    if (isGeneral) {
      node.classList.add("container-general");
    }

    if (sidebarMenu && !isGeneral) {
      const navIndex = normalContainerNodes.length;
      const navButton = document.createElement("button");
      navButton.type = "button";
      navButton.className = "sidebar-nav-btn";
      navButton.textContent = container.title || `Contenedor ${index + 1}`;
      navButton.addEventListener("click", () => {
        selectContainer(navIndex);
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
        if (Array.isArray(widget.controls)) {
          widget.controls.forEach((el) => {
            if (el) {
              controlElements.add(el);
            }
          });
        }
      }
    });

    containerNodes.push(node);
    if (isGeneral) {
      generalContainerNodes.push(node);
    } else {
      normalContainerNodes.push(node);
    }
  });

  // Colocar el general arriba del grid; los normales dentro del scada-container
  if (generalContainerNodes.length && scadaGrid) {
    generalContainerNodes.forEach((node) => {
      scadaGrid.insertBefore(node, scadaContainer);
    });
  }
  normalContainerNodes.forEach((node) => scadaContainer.appendChild(node));

  if (normalContainerNodes.length) {
    selectContainer(Math.min(selectedContainerIndex, normalContainerNodes.length - 1));
  } else {
    updateSidebarVisibility();
    if (sidebarMenu) {
      sidebarMenu.hidden = true;
    }
  }

  renderView(currentView);
  applyScopedTopics();
}

function selectContainer(index) {
  if (!normalContainerNodes.length) {
    selectedContainerIndex = 0;
    updateSidebarMenuState();
    updateSidebarVisibility();
    return;
  }
  const clamped = Math.max(0, Math.min(index, normalContainerNodes.length - 1));
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
  const showNode = (node) => {
    node.removeAttribute("hidden");
    node.style.display = "";
    node.removeAttribute("aria-hidden");
  };
  const hideNode = (node) => {
    node.classList.remove("sidebar-active");
    node.setAttribute("hidden", "");
    node.style.display = "none";
    node.setAttribute("aria-hidden", "true");
  };
  const trackedGeneral = generalContainerNodes.length
    ? generalContainerNodes
    : Array.from(scadaContainer.querySelectorAll('.container-card')).filter((node) => node.dataset.isGeneral === "true");
  const trackedNormal = normalContainerNodes.length
    ? normalContainerNodes
    : Array.from(scadaContainer.querySelectorAll('.container-card')).filter((node) => node.dataset.isGeneral !== "true");

  const activeIndex = trackedNormal.length
    ? Math.max(0, Math.min(selectedContainerIndex, trackedNormal.length - 1))
    : 0;
  selectedContainerIndex = activeIndex;

  if (isSidebar) {
    trackedGeneral.forEach((node) => {
      node.classList.add("sidebar-active");
      showNode(node);
    });
    trackedNormal.forEach((node, idx) => {
      const isActive = idx === activeIndex;
      node.classList.toggle("sidebar-active", isActive);
      if (isActive) {
        showNode(node);
      } else {
        hideNode(node);
      }
    });
  } else {
    trackedGeneral.forEach(showNode);
    trackedNormal.forEach((node) => {
      node.classList.remove("sidebar-active");
      showNode(node);
    });
  }

  const extras = Array.from(scadaContainer.querySelectorAll(".container-card")).filter(
    (node) => !trackedGeneral.includes(node) && !trackedNormal.includes(node)
  );
  extras.forEach((node) => {
    if (isSidebar) {
      hideNode(node);
    } else {
      showNode(node);
    }
  });
}

function buildWidget(definition, containerIndex, objectIndex) {
  const { type, topic, label, unit, min, max, color, onColor, offColor, payload, feedbackTopic, onText, offText } = definition;
  const widgetId = `c${containerIndex}-o${objectIndex}`;
  const relTopic = topic || "";
  const normalizedTopic = normalizeRelativePath(relTopic);
  const normalizedFeedbackTopic = feedbackTopic ? normalizeRelativePath(feedbackTopic) : null;
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
    case "valuepublisher": {
      const widget = createValuePublisher(
        `${widgetId}-publisher`,
        label || "Publicar valor",
        unit || "",
        normalizedTopic,
        normalizedFeedbackTopic
      );
      return { element: widget.element, controls: widget.controls, binding: widget.binding };
    }
    case "slide": {
      const widget = createBooleanSlide(`${widgetId}-slide`, {
        label: label || "Control",
        topic: normalizedTopic,
        readTopic: normalizedFeedbackTopic || normalizedTopic,
        onText,
        offText
      });
      const result = { element: widget.element };
      if (Array.isArray(widget.controls) && widget.controls.length) {
        result.controls = widget.controls;
      }
      if (widget.binding) {
        result.binding = widget.binding;
      }
      return result;
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

function createBooleanSlide(id, { label, topic, readTopic, onText, offText }) {
  const wrapper = document.createElement("div");
  wrapper.className = "bool-slide";

  const header = document.createElement("div");
  header.className = "bool-slide__header";

  const titleEl = document.createElement("span");
  titleEl.className = "bool-slide__title";
  titleEl.textContent = label || "Control";
  header.appendChild(titleEl);

  const stateEl = document.createElement("span");
  stateEl.className = "bool-slide__state";
  header.appendChild(stateEl);

  wrapper.appendChild(header);

  const controlEl = document.createElement("div");
  controlEl.className = "bool-slide__control";

  const inputEl = document.createElement("input");
  inputEl.type = "checkbox";
  inputEl.id = id;
  inputEl.className = "bool-slide__input";
  controlEl.appendChild(inputEl);

  const sliderLabel = document.createElement("label");
  sliderLabel.className = "bool-slide__slider";
  sliderLabel.setAttribute("for", id);
  sliderLabel.innerHTML = '<span class="bool-slide__track"></span><span class="bool-slide__thumb"></span>';
  controlEl.appendChild(sliderLabel);

  wrapper.appendChild(controlEl);

  const feedbackEl = document.createElement("p");
  feedbackEl.className = "bool-slide__feedback";
  feedbackEl.textContent = "";
  wrapper.appendChild(feedbackEl);

  const resolvedOnText = typeof onText === "string" && onText.trim() ? onText.trim() : "Encendido";
  const resolvedOffText = typeof offText === "string" && offText.trim() ? offText.trim() : "Apagado";

  let currentState = false;
  let requestedState = null;
  let feedbackTimer = null;

  const coerceBoolean = (value) => {
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (!normalized) return null;
      if (["1", "true", "on", "encendido", "si", "sí", "habilitado"].includes(normalized)) return true;
      if (["0", "false", "off", "apagado", "no", "disabled", "deshabilitado"].includes(normalized)) return false;
    }
    return null;
  };

  const updateStateVisuals = (state) => {
    inputEl.checked = state;
    stateEl.textContent = state ? resolvedOnText : resolvedOffText;
    wrapper.dataset.state = state ? "on" : "off";
  };

  const clearFeedbackTimer = () => {
    if (feedbackTimer) {
      clearTimeout(feedbackTimer);
      feedbackTimer = null;
    }
  };

  const setFeedback = (message, tone, duration = 3500) => {
    clearFeedbackTimer();
    feedbackEl.textContent = message || "";
    if (tone) {
      feedbackEl.dataset.tone = tone;
    } else {
      delete feedbackEl.dataset.tone;
    }
    if (message && tone && duration > 0) {
      feedbackTimer = setTimeout(() => {
        feedbackEl.textContent = "";
        delete feedbackEl.dataset.tone;
        feedbackTimer = null;
      }, duration);
    }
  };

  const setPending = (value) => {
    if (value) {
      wrapper.dataset.pending = "true";
    } else {
      delete wrapper.dataset.pending;
    }
  };

  const applyState = (value) => {
    const normalized = coerceBoolean(value);
    if (normalized === null) return;
    currentState = normalized;
    requestedState = null;
    setPending(false);
    updateStateVisuals(normalized);
  };

  inputEl.addEventListener("change", () => {
    if (!topic) {
      setFeedback("Configura un topic para publicar.", "error", 0);
      updateStateVisuals(currentState);
      return;
    }
    if (currentRole === "viewer" || currentRole === "visualizacion") {
      setFeedback("Rol sin permisos de control.", "error");
      updateStateVisuals(currentState);
      return;
    }
    const nextState = inputEl.checked;
    requestedState = nextState;
    updateStateVisuals(nextState);
    if (readTopic) {
      setPending(true);
    } else {
      currentState = nextState;
    }
    const payload = nextState ? 1 : 0;
    publishRelative(topic, payload);
    setFeedback(`Comando enviado: ${nextState ? resolvedOnText : resolvedOffText} (${payload})`, "success");
  });

  updateStateVisuals(currentState);

  if (!topic) {
    inputEl.disabled = true;
    inputEl.dataset.locked = "true";
    inputEl.classList.add("control-disabled");
    setFeedback("Topic no configurado para publicar.", "error", 0);
  }

  if (!readTopic) {
    setPending(false);
    setFeedback("Lectura no configurada.", "info", 0);
  }

  return {
    element: wrapper,
    controls: [inputEl],
    binding: readTopic ? { topic: readTopic, update: applyState } : null
  };
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

function createValuePublisher(id, label, unit, topic, readTopic) {
  const wrapper = document.createElement("div");
  wrapper.className = "value-publisher";

  const normalizedUnit = typeof unit === "string" ? unit : "";
  const unitSuffix = normalizedUnit ? ` ${normalizedUnit}` : "";

  const header = document.createElement("div");
  header.className = "publisher-header";

  const labelSpan = document.createElement("span");
  labelSpan.className = "publisher-label";
  labelSpan.textContent = label || "Publicar valor";
  header.appendChild(labelSpan);

  const unitSpan = document.createElement("span");
  unitSpan.className = "publisher-unit";
  unitSpan.textContent = normalizedUnit;
  unitSpan.hidden = !normalizedUnit;
  header.appendChild(unitSpan);

  wrapper.appendChild(header);

  const currentValue = document.createElement("p");
  currentValue.className = "publisher-current";
  if (readTopic) {
    currentValue.textContent = `Valor actual --${unitSuffix}`;
    currentValue.dataset.state = "idle";
  } else {
    currentValue.textContent = "Lectura no configurada";
    currentValue.dataset.state = "disabled";
  }
  wrapper.appendChild(currentValue);

  const inputGroup = document.createElement("div");
  inputGroup.className = "publisher-input-group";

  const input = document.createElement("input");
  input.type = "number";
  input.step = "any";
  input.inputMode = "decimal";
  input.id = `${id}-input`;
  input.placeholder = "0";
  input.className = "publisher-input";
  inputGroup.appendChild(input);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn publisher-send";
  button.textContent = "Enviar";
  inputGroup.appendChild(button);

  wrapper.appendChild(inputGroup);

  const feedback = document.createElement("p");
  feedback.className = "publisher-feedback";
  feedback.textContent = "";
  wrapper.appendChild(feedback);

  let feedbackTimer = null;
  const clearFeedbackTimer = () => {
    if (feedbackTimer) {
      clearTimeout(feedbackTimer);
      feedbackTimer = null;
    }
  };

  const setFeedback = (message, tone) => {
    clearFeedbackTimer();
    feedback.textContent = message || "";
    if (tone) {
      feedback.dataset.tone = tone;
    } else {
      delete feedback.dataset.tone;
    }
    if (message && tone) {
      feedbackTimer = setTimeout(() => {
        feedback.textContent = "";
        delete feedback.dataset.tone;
        feedbackTimer = null;
      }, 3500);
    }
  };

  const parseInput = () => {
    const raw = input.value.replace(",", ".").trim();
    if (!raw) {
      return { ok: false, error: "Ingresa un valor." };
    }
    const numeric = Number(raw);
    if (!Number.isFinite(numeric)) {
      return { ok: false, error: "Valor no valido." };
    }
    return { ok: true, value: numeric };
  };

  const formatFeedbackValue = (raw) => {
    if (raw === undefined || raw === null || raw === "") {
      return "--";
    }
    const numeric = Number(raw);
    if (Number.isFinite(numeric)) {
      return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
    }
    return String(raw);
  };

  const applyCurrentValue = (value) => {
    if (!readTopic) return;
    const formatted = formatFeedbackValue(value);
    currentValue.textContent = `Valor actual ${formatted}${unitSuffix}`;
    if (formatted === "--") {
      currentValue.dataset.state = "idle";
    } else {
      currentValue.dataset.state = "active";
    }
  };

  const sendValue = () => {
    if (!topic) {
      setFeedback("Configura un topic para publicar.", "error");
      return;
    }
    if (currentRole === "viewer" || currentRole === "visualizacion") {
      setFeedback("Rol sin permisos de control.", "error");
      return;
    }
    const parsed = parseInput();
    if (!parsed.ok) {
      setFeedback(parsed.error, "error");
      return;
    }
    const payload = Number.isInteger(parsed.value) ? Math.trunc(parsed.value) : parsed.value;
    publishRelative(topic, payload);
    setFeedback(`Valor enviado: ${payload}${unitSuffix}`, "success");
  };

  button.addEventListener("click", sendValue);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      sendValue();
    }
  });

  if (!topic) {
    input.disabled = true;
    input.dataset.locked = "true";
    button.disabled = true;
    button.dataset.locked = "true";
    setFeedback("Topic no configurado para este widget.", "error");
  }

  return {
    element: wrapper,
    controls: [input, button],
    binding: readTopic ? { topic: readTopic, update: applyCurrentValue } : null
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
  const hasNavigable = normalContainerNodes.length > 0;
  if (sidebarMenu) {
    sidebarMenu.hidden = view !== "sidebar" || !hasNavigable;
  }
  if (view === "sidebar") {
    if (hasNavigable) {
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
    const { config, role, empresaId, plants, accessiblePlants: allowedPlants } = await fetchScadaConfig(user, forceRefresh);
    const resolvedTitle = persistMainTitle(config.mainTitle || DEFAULT_MAIN_TITLE);
    if (mainTitleNode) {
      mainTitleNode.textContent = resolvedTitle;
    }
    document.title = resolvedTitle;
    currentRole = role || "operador";
    const resolvedEmpresa = empresaId || currentCompanyId;
    setAvailablePlants(plants && plants.length ? plants : config.plants || [], allowedPlants || [], resolvedEmpresa);
    clearDashboard();
    renderDashboard();
    updateRoleUI();
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
  canAccessCotizador = false;
  uid = null;
  availablePlants = [];
  accessiblePlantIds = [];
  selectedPlantId = null;
  clearDashboard();
  scadaContainer.innerHTML = '<p class="empty-state">Inicia sesion para cargar tu tablero SCADA.</p>';
  if (sidebarMenu) {
    sidebarMenu.hidden = true;
  }
  if (mainTitleNode) {
    mainTitleNode.textContent = DEFAULT_MAIN_TITLE;
  }
  document.title = DEFAULT_MAIN_TITLE;
  clearStoredMainTitle();
  clearBrandLogo(DEFAULT_MAIN_TITLE);
  updateConnectionChip(false);
  setCurrentUser();
  updateRoleUI();
  updatePlantSelectorUI();
  if (configLink) {
    configLink.hidden = true;
  }
  if (trendLink) {
    trendLink.hidden = true;
  }
  if (cotizadorLink) {
    cotizadorLink.hidden = true;
  }
}

handleViewToggle();
setupLoginDialog();
plantSelect?.addEventListener("change", handlePlantChange);

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













