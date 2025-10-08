const BACKEND_HTTP = "https://scadawebdesk.onrender.com";

const OBJECT_TYPES = [
  {
    value: "level",
    label: "Indicador de nivel",
    hint: "Barra vertical para porcentajes o volumen",
    defaults: { type: "level", label: "Nivel", topic: "", unit: "%", min: 0, max: 100, color: "#00b4d8" },
    fields: [
      { key: "label", label: "Nombre visible", type: "text", placeholder: "Nivel Estanque", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/Nivel", section: "primary" },
      { key: "unit", label: "Unidad", type: "text", placeholder: "%, m3", section: "primary" },
      { key: "color", label: "Color", type: "color", section: "primary" },
      { key: "min", label: "Valor minimo", type: "number", section: "advanced" },
      { key: "max", label: "Valor maximo", type: "number", section: "advanced" },
    ],
  },
  {
    value: "gauge",
    label: "Indicador semicurva",
    hint: "Medidor semicircular con limites personalizados",
    defaults: { type: "gauge", label: "Indicador", topic: "", unit: "", min: 0, max: 100, color: "#00b4d8" },
    fields: [
      { key: "label", label: "Nombre visible", type: "text", placeholder: "Presion linea", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/Presion", section: "primary" },
      { key: "unit", label: "Unidad", type: "text", placeholder: "bar, psi", section: "primary" },
      { key: "color", label: "Color", type: "color", section: "primary" },
      { key: "min", label: "Valor minimo", type: "number", section: "advanced" },
      { key: "max", label: "Valor maximo", type: "number", section: "advanced" },
    ],
  },
  {
    value: "number",
    label: "Numero en linea",
    hint: "Muestra el ultimo valor numerico recibido",
    defaults: { type: "number", label: "Valor", topic: "", unit: "" },
    fields: [
      { key: "label", label: "Nombre visible", type: "text", placeholder: "Caudal instante", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/Caudal", section: "primary" },
      { key: "unit", label: "Unidad", type: "text", placeholder: "m3/h", section: "primary" },
    ],
  },
  {
    value: "text",
    label: "Texto libre",
    hint: "Ideal para estados o mensajes",
    defaults: { type: "text", label: "Texto", topic: "" },
    fields: [
      { key: "label", label: "Nombre visible", type: "text", placeholder: "Estado PLC", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/Estado", section: "primary" },
    ],
  },
  {
    value: "motorSpeed",
    label: "Velocidad de motor",
    hint: "Valor numerico pensado para RPM",
    defaults: { type: "motorSpeed", label: "Velocidad", topic: "", unit: "rpm" },
    fields: [
      { key: "label", label: "Nombre visible", type: "text", placeholder: "Motor bomba", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/Velocidad", section: "primary" },
      { key: "unit", label: "Unidad", type: "text", placeholder: "rpm", section: "primary" },
    ],
  },
  {
    value: "pumpStatus",
    label: "Estado binario",
    hint: "Muestra ON/OFF con colores",
    defaults: { type: "pumpStatus", label: "Estado", topic: "", onColor: "#00ff9d", offColor: "#6c757d" },
    fields: [
      { key: "label", label: "Nombre visible", type: "text", placeholder: "Estado Bomba", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/PumpSts", section: "primary" },
      { key: "onColor", label: "Color encendido", type: "color", section: "primary" },
      { key: "offColor", label: "Color apagado", type: "color", section: "primary" },
    ],
  },
  {
    value: "startBtn",
    label: "Boton iniciar",
    hint: "Publica un comando para arrancar",
    defaults: { type: "startBtn", label: "Partir", topic: "", color: "#00b4d8", payload: "1" },
    fields: [
      { key: "label", label: "Texto del boton", type: "text", placeholder: "Partir equipo", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/CmdStart", section: "primary" },
      { key: "color", label: "Color del boton", type: "color", section: "primary" },
      { key: "payload", label: "Payload a enviar", type: "text", placeholder: "1", section: "advanced" },
    ],
  },
  {
    value: "stopBtn",
    label: "Boton detener",
    hint: "Publica un comando de paro",
    defaults: { type: "stopBtn", label: "Detener", topic: "", color: "#ef476f", payload: "0" },
    fields: [
      { key: "label", label: "Texto del boton", type: "text", placeholder: "Parar equipo", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/CmdStop", section: "primary" },
      { key: "color", label: "Color del boton", type: "color", section: "primary" },
      { key: "payload", label: "Payload a enviar", type: "text", placeholder: "0", section: "advanced" },
    ],
  },
  {
    value: "resetBtn",
    label: "Boton reset",
    hint: "Envia un comando de reinicio",
    defaults: { type: "resetBtn", label: "Reset", topic: "", color: "#ffd166", payload: "reset" },
    fields: [
      { key: "label", label: "Texto del boton", type: "text", placeholder: "Reset alarma", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "Linea1/CmdReset", section: "primary" },
      { key: "color", label: "Color del boton", type: "color", section: "primary" },
      { key: "payload", label: "Payload a enviar", type: "text", placeholder: "reset", section: "advanced" },
    ],
  },
];

const OBJECT_TYPE_MAP = new Map(OBJECT_TYPES.map((item) => [item.value.toLowerCase(), item]));

const state = {
  token: null,
  empresaId: null,
  claimEmpresaId: null,
  role: "viewer",
  isMaster: false,
  canEdit: false,
  dirty: false,
  tenants: [],
  tenantsLoaded: false,
  tenantLoading: false,
  editingTenantId: null,
  config: createEmptyConfig(),
};

const dom = {
  root: document.getElementById("config-root"),
  statusBanner: document.getElementById("status-banner"),
  sessionStatus: document.getElementById("session-status"),
  roleBadge: document.getElementById("role-badge"),
  logoutBtn: document.getElementById("logout-btn"),
  openLoginBtn: document.getElementById("open-login"),
  closeLoginBtn: document.getElementById("close-login"),
  loginDialog: document.getElementById("login-dialog"),
  loginForm: document.getElementById("login-form"),
  emailInput: document.getElementById("email"),
  passwordInput: document.getElementById("password"),
  mainTitle: document.getElementById("mainTitle"),
  rolesAdmins: document.getElementById("roles-admins"),
  rolesOperators: document.getElementById("roles-operators"),
  rolesViewers: document.getElementById("roles-viewers"),
  addContainer: document.getElementById("add-container"),
  expandCollapse: document.getElementById("expand-collapse"),
  containersList: document.getElementById("containers-list"),
  containersEmpty: document.getElementById("containers-empty"),
  containerTemplate: document.getElementById("container-template"),
  objectTemplate: document.getElementById("object-template"),
  reloadBtn: document.getElementById("reload-btn"),
  saveBtn: document.getElementById("save-btn"),
  downloadBtn: document.getElementById("download-btn"),
  importBtn: document.getElementById("import-btn"),
  importInput: document.getElementById("importInput"),
  masterPanel: document.getElementById("master-panel"),
  refreshTenantsBtn: document.getElementById("refresh-tenants"),
  resetTenantFormBtn: document.getElementById("reset-tenant-form"),
  tenantList: document.getElementById("tenant-list"),
  tenantForm: document.getElementById("tenant-form"),
  tenantFormTitle: document.getElementById("tenant-form-title"),
  tenantEmpresaId: document.getElementById("tenant-empresa-id"),
  tenantName: document.getElementById("tenant-name"),
  tenantCloneFrom: document.getElementById("tenant-clone-from"),
  tenantActive: document.getElementById("tenant-active"),
  tenantDescription: document.getElementById("tenant-description"),
  tenantMode: document.getElementById("tenant-mode"),
  tenantStatus: document.getElementById("tenant-form-status"),
  tenantSubmit: document.getElementById("tenant-submit-btn"),
};

function updateRoleBadge() {
  if (!dom.roleBadge) return;
  const roleLabel = state.isMaster ? "master" : (state.role || "viewer");
  dom.roleBadge.textContent = roleLabel.toUpperCase();
}

function applyPermissions() {
  const root = dom.root;
  const canEdit = Boolean(state.canEdit);
  if (root) {
    root.classList.toggle("readonly", !canEdit);
  }
  const toggleElements = [
    dom.saveBtn,
    dom.addContainer,
    dom.expandCollapse,
    dom.importBtn,
    dom.downloadBtn,
  ];
  toggleElements.forEach((element) => {
    if (!element) return;
    if (canEdit) {
      element.removeAttribute("disabled");
    } else {
      element.setAttribute("disabled", "");
    }
  });
  dom.containersList?.classList.toggle("is-readonly", !canEdit);
}


let containerUiState = new WeakMap();


document.addEventListener("DOMContentLoaded", () => {
  attachStaticHandlers();
  firebase.auth().onAuthStateChanged(onAuthStateChanged);
});
function attachStaticHandlers() {
  dom.reloadBtn?.addEventListener("click", () => loadConfig(true));
  dom.saveBtn?.addEventListener("click", saveConfig);
  dom.downloadBtn?.addEventListener("click", downloadConfig);
  dom.importBtn?.addEventListener("click", () => dom.importInput?.click());
  dom.importInput?.addEventListener("change", handleImportFile);
  dom.addContainer?.addEventListener("click", () => {
    addContainer();
    setDirty(true);
  });
  dom.expandCollapse?.addEventListener("click", toggleAllContainers);
  dom.mainTitle?.addEventListener("input", (event) => {
    state.config.mainTitle = event.target.value;
    setDirty(true);
  });
  dom.rolesAdmins?.addEventListener("input", () => updateRolesFromInputs());
  dom.rolesOperators?.addEventListener("input", () => updateRolesFromInputs());
  dom.rolesViewers?.addEventListener("input", () => updateRolesFromInputs());
  dom.openLoginBtn?.addEventListener("click", () => {
    if (!firebase.auth().currentUser) {
      dom.loginDialog?.showModal();
    }
  });
  dom.closeLoginBtn?.addEventListener("click", () => {
    dom.loginDialog?.close();
    dom.loginForm?.reset();
  });
  dom.loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = dom.emailInput?.value.trim();
    const password = dom.passwordInput?.value;
    if (!email || !password) {
      setStatus("Email y contrasena requeridos", "warning");
      return;
    }
    try {
      await firebase.auth().signInWithEmailAndPassword(email, password);
      dom.loginDialog?.close();
      dom.loginForm?.reset();
      setStatus("Sesion iniciada.", "success");
    } catch (error) {
      setStatus((error && error.message) || "No se pudo iniciar sesion", "error");
    }
  });
  dom.logoutBtn?.addEventListener("click", async () => {
    try {
      await firebase.auth().signOut();
    } catch (error) {
      console.error("logout", error);
    }
  });
  dom.containersList?.addEventListener("click", handleContainerActions);
  dom.refreshTenantsBtn?.addEventListener("click", () => loadTenants(true));
  dom.resetTenantFormBtn?.addEventListener("click", () => resetTenantForm("create"));
  dom.tenantForm?.addEventListener("submit", submitTenantForm);
  dom.tenantList?.addEventListener("click", handleTenantListClick);
}

async function onAuthStateChanged(user) {
  if (user) {
    dom.sessionStatus.textContent = "Sesion activa: " + user.email;
    dom.logoutBtn?.removeAttribute("disabled");
    dom.openLoginBtn?.setAttribute("disabled", "");
    state.claimEmpresaId = null;
    state.empresaId = null;
    state.isMaster = false;
    state.tenants = [];
    state.tenantsLoaded = false;
    state.tenantLoading = false;
    state.editingTenantId = null;
    renderMasterPanel();
    await refreshToken(user);
    await loadConfig();
    if (state.isMaster) {
      loadTenants().catch((err) => console.error("loadTenants", err));
    }
  } else {
    dom.sessionStatus.textContent = "Sin sesion";
    dom.logoutBtn?.setAttribute("disabled", "");
    dom.openLoginBtn?.removeAttribute("disabled");
    state.token = null;
    state.empresaId = null;
    state.claimEmpresaId = null;
    state.role = "viewer";
    state.isMaster = false;
    state.canEdit = false;
    state.config = createEmptyConfig();
    state.tenants = [];
    state.tenantsLoaded = false;
    state.tenantLoading = false;
    state.editingTenantId = null;
    containerUiState = new WeakMap();
    setDirty(false);
    updateRoleBadge();
    applyPermissions();
    renderAll();
    renderMasterPanel();
    setTenantStatus("");
    setStatus("Autenticate para cargar la configuracion.", "info");
  }
}

async function refreshToken(user) {
  if (!user) {
    state.token = null;
    return null;
  }
  state.token = await user.getIdToken(true);
  return state.token;
}

async function loadConfig(force = false, targetEmpresaId = null) {
  const user = firebase.auth().currentUser;
  if (!user) return;
  try {
    if (!state.token || force) {
      await refreshToken(user);
    }
    const empresaId = targetEmpresaId ?? (state.isMaster && state.empresaId ? state.empresaId : null);
    const query = empresaId ? `?empresaId=${encodeURIComponent(empresaId)}` : "";
    setStatus("Cargando configuracion...", "info");
    const response = await fetch(BACKEND_HTTP + "/config" + query, {
      headers: {
        Authorization: "Bearer " + state.token,
      },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || orFallback(response.status));
    }
    const payload = await response.json();
    const config = normalizeConfig(payload.config || {});
    state.isMaster = Boolean(payload.isMaster);
    if (!state.isMaster) {
      state.tenants = [];
      state.tenantsLoaded = false;
      state.tenantLoading = false;
      state.editingTenantId = null;
      setTenantStatus("");
    }
    if (!state.claimEmpresaId && payload.empresaId) {
      state.claimEmpresaId = payload.empresaId;
    }
    state.empresaId = (payload.empresaId || config.empresaId || empresaId || state.empresaId || "").toString().trim();
    state.role = payload.role || determineRole(config, user.email);
    state.canEdit = state.role === "admin";
    state.config = config;
    state.config.empresaId = state.empresaId;
    containerUiState = new WeakMap();
    setDirty(false);
    updateRoleBadge();
    applyPermissions();
    renderAll();
    if (state.isMaster) {
      renderMasterPanel();
    }
    const statusMessage = state.canEdit ? "Configuracion cargada. Puedes editar." : "Configuracion cargada en modo lectura.";
    const statusContext = state.empresaId ? `${statusMessage} (Empresa: ${state.empresaId})` : statusMessage;
    setStatus(statusContext, state.canEdit ? "success" : "info");
  } catch (error) {
    console.error("loadConfig", error);
    setStatus("No se pudo cargar: " + ((error && error.message) || error), "error");
  }
}



function handleImportFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const text = String((e.target && e.target.result) || "");
      const parsed = JSON.parse(text);
      const normalized = normalizeConfig(parsed);
      state.config = normalized;
      state.empresaId = normalized.empresaId || state.empresaId;
      state.config.empresaId = state.empresaId;
      containerUiState = new WeakMap();
      setDirty(true);
      renderAll();
      setStatus("Archivo importado. Revisa y guarda para aplicar.", "info");
    } catch (error) {
      console.error("import", error);
      setStatus("Archivo invalido: " + error.message, "error");
    }
  };
  reader.readAsText(file, "utf-8");
  event.target.value = "";
}
function normalizeConfig(raw) {
  const base = createEmptyConfig();
  if (!raw || typeof raw !== "object") {
    return base;
  }
  if (typeof raw.empresaId === "string") {
    base.empresaId = raw.empresaId.trim();
  } else if (typeof raw.empresa_id === "string") {
    base.empresaId = raw.empresa_id.trim();
  }
  if (typeof raw.mainTitle === "string") {
    base.mainTitle = raw.mainTitle;
  }
  const roles = raw.roles || {};
  base.roles = {
    admins: emailsFrom(roles.admins),
    operators: emailsFrom(roles.operators),
    viewers: emailsFrom(roles.viewers),
  };
  if (Array.isArray(raw.containers)) {
    base.containers = raw.containers.map((container) => normalizeContainer(container));
  }
  return base;
}

function normalizeContainer(raw) {
  const result = {
    title: typeof raw?.title === "string" ? raw.title : "",
    objects: [],
  };
  if (Array.isArray(raw?.objects)) {
    result.objects = raw.objects.map((object) => normalizeObject(object));
  }
  return result;
}

function normalizeObject(raw) {
  if (!raw || typeof raw !== "object") {
    return { type: "text", label: "", topic: "" };
  }
  const type = raw.type || "text";
  const meta = resolveObjectMeta(type);
  const defaults = clone(meta.defaults || {});
  const merged = Object.assign({}, defaults, raw);
  if (!merged.type) {
    merged.type = meta.value || type;
  }
  return merged;
}

function createEmptyConfig() {
  return {
    empresaId: "",
    mainTitle: "",
    roles: {
      admins: [],
      operators: [],
      viewers: [],
    },
    containers: [],
  };
}

function orFallback(code) {
  return "Error " + code;
}
function escapeHtml(value) {
  if (value === undefined || value === null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeCssEscape(value) {
  if (typeof value !== "string") return "";
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return value.replace(/[^a-zA-Z0-9_-]/g, (match) => `\\${match}`);
}

async function loadTenants(force = false) {
  if (!state.isMaster || !dom.masterPanel) return;
  if (state.tenantLoading) return;
  if (state.tenantsLoaded && !force) {
    renderTenantList();
    populateTenantCloneOptions();
    return;
  }
  if (!state.token) return;
  state.tenantLoading = true;
  setTenantStatus("Cargando clientes...", "info");
  try {
    const response = await fetch(BACKEND_HTTP + "/tenants", {
      headers: {
        Authorization: "Bearer " + state.token,
      },
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(detail || orFallback(response.status));
    }
    const payload = await response.json();
    const companies = Array.isArray(payload.companies) ? payload.companies : [];
    state.tenants = companies.sort((a, b) => {
      const nameA = (a.name || a.empresaId || "").toLowerCase();
      const nameB = (b.name || b.empresaId || "").toLowerCase();
      if (nameA < nameB) return -1;
      if (nameA > nameB) return 1;
      return 0;
    });
    state.tenantsLoaded = true;
    renderTenantList();
    populateTenantCloneOptions();
    setTenantStatus("Lista actualizada", "success");
  } catch (error) {
    console.error("loadTenants", error);
    setTenantStatus("No se pudo cargar la lista: " + ((error && error.message) || error), "error");
  } finally {
    state.tenantLoading = false;
  }
}

function renderMasterPanel() {
  if (!dom.masterPanel) return;
  if (!state.isMaster) {
    dom.masterPanel.hidden = true;
    return;
  }
  dom.masterPanel.hidden = false;
  if (!state.editingTenantId) {
    resetTenantForm("create");
  }
  if (!state.tenantsLoaded && !state.tenantLoading) {
    loadTenants().catch((err) => console.error("loadTenants", err));
  } else {
    renderTenantList();
    populateTenantCloneOptions();
  }
  updateTenantFormHeader();
}

function renderTenantList() {
  if (!dom.tenantList) return;
  if (!state.tenants || !state.tenants.length) {
    dom.tenantList.innerHTML = '<li class="tenant-item"><div class="tenant-item__header"><h4 class="tenant-item__title">Sin clientes registrados</h4></div><div class="tenant-item__meta">Crea uno nuevo desde el formulario.</div></li>';
    return;
  }
  dom.tenantList.innerHTML = state.tenants
    .map((tenant) => {
      const title = escapeHtml(tenant.name || tenant.empresaId);
      const description = tenant.description ? `<div class="tenant-item__meta">${escapeHtml(tenant.description)}</div>` : "";
      const activeLabel = tenant.active ? 'Activo' : 'Inactivo';
      const badge = `<span class="tenant-badge">${escapeHtml(tenant.empresaId)}</span>`;
      const meta = `<div class="tenant-item__meta">${escapeHtml(activeLabel)}</div>`;
      const isActive = state.empresaId && state.empresaId === tenant.empresaId;
      const activeClass = isActive ? ' tenant-item--active' : '';
      return `
      <li class="tenant-item${activeClass}">
        <div class="tenant-item__header">
          <h4 class="tenant-item__title">${title}</h4>
          ${badge}
        </div>
        ${meta}
        ${description}
        <div class="tenant-item__actions">
          <button type="button" class="btn btn-link" data-action="switch" data-empresa="${escapeHtml(tenant.empresaId)}">Seleccionar</button>
          <button type="button" class="btn btn-link" data-action="edit" data-empresa="${escapeHtml(tenant.empresaId)}">Editar</button>
        </div>
      </li>`;
    })
    .join("");
}

function populateTenantCloneOptions() {
  if (!dom.tenantCloneFrom) return;
  const current = dom.tenantCloneFrom.value;
  const options = (state.tenants || [])
    .map((tenant) => `<option value="${escapeHtml(tenant.empresaId)}">${escapeHtml(tenant.name || tenant.empresaId)}</option>`)
    .join("");
  dom.tenantCloneFrom.innerHTML = '<option value="">Config base (DEFAULT)</option>' + options;
  if (current && dom.tenantCloneFrom.querySelector(`option[value="${safeCssEscape(current)}"]`)) {
    dom.tenantCloneFrom.value = current;
  }
}

function resetTenantForm(mode = "create") {
  if (!dom.tenantForm) return;
  dom.tenantForm.reset();
  if (dom.tenantMode) {
    dom.tenantMode.value = mode;
  }
  state.editingTenantId = mode === "update" ? state.editingTenantId : null;
  if (dom.tenantEmpresaId) {
    dom.tenantEmpresaId.disabled = mode === "update";
    if (mode === "create") {
      dom.tenantEmpresaId.value = "";
    }
  }
  if (dom.tenantActive) {
    dom.tenantActive.value = "true";
  }
  if (dom.tenantDescription) {
    dom.tenantDescription.value = "";
  }
  if (dom.tenantCloneFrom) {
    dom.tenantCloneFrom.value = "";
  }
  setTenantStatus("");
  updateTenantFormHeader();
}

function fillTenantForm(tenant) {
  if (!tenant) return;
  state.editingTenantId = tenant.empresaId;
  if (dom.tenantMode) {
    dom.tenantMode.value = "update";
  }
  if (dom.tenantEmpresaId) {
    dom.tenantEmpresaId.value = tenant.empresaId;
    dom.tenantEmpresaId.disabled = true;
  }
  if (dom.tenantName) {
    dom.tenantName.value = tenant.name || "";
  }
  if (dom.tenantDescription) {
    dom.tenantDescription.value = tenant.description || "";
  }
  if (dom.tenantActive) {
    dom.tenantActive.value = tenant.active ? "true" : "false";
  }
  setTenantStatus("Editando cliente " + tenant.empresaId);
  updateTenantFormHeader();
}

function updateTenantFormHeader() {
  if (!dom.tenantFormTitle || !dom.tenantSubmit) return;
  const mode = dom.tenantMode.value || "create";
  if (mode === "update" && state.editingTenantId) {
    dom.tenantFormTitle.textContent = "Editar cliente";
    dom.tenantSubmit.textContent = "Guardar cambios";
  } else {
    dom.tenantFormTitle.textContent = "Crear cliente";
    dom.tenantSubmit.textContent = "Crear cliente";
  }
}

function setTenantStatus(message, type = "info") {
  if (!dom.tenantStatus) return;
  dom.tenantStatus.textContent = message || "";
  switch (type) {
    case "success":
      dom.tenantStatus.style.color = "#6cffd6";
      break;
    case "error":
      dom.tenantStatus.style.color = "#ff9fb4";
      break;
    default:
      dom.tenantStatus.style.color = "var(--text-muted)";
  }
}

async function submitTenantForm(event) {
  event.preventDefault();
  if (!state.token) {
    setTenantStatus("Sesion expirada. Vuelve a iniciar sesion.", "error");
    return;
  }
  if (!dom.tenantEmpresaId || !dom.tenantActive) {
    setTenantStatus("Formulario no disponible", "error");
    return;
  }
  const mode = dom.tenantMode?.value || "create";
  const empresaId = dom.tenantEmpresaId.value.trim();
  const name = dom.tenantName?.value?.trim() || "";
  const description = dom.tenantDescription?.value?.trim() || "";
  const active = dom.tenantActive.value === "true";
  const cloneFrom = dom.tenantCloneFrom?.value?.trim() || "";
  if (!empresaId && mode === "create") {
    setTenantStatus("Debes indicar un empresaId.", "error");
    dom.tenantEmpresaId.focus();
    return;
  }
  try {
    setTenantStatus(mode === "create" ? "Creando cliente..." : "Actualizando cliente...", "info");
    let response;
    if (mode === "create") {
      const payload = { empresaId, name, description, active, cloneFrom: cloneFrom || undefined };
      response = await fetch(BACKEND_HTTP + "/tenants", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + state.token,
        },
        body: JSON.stringify(payload),
      });
    } else {
      if (!state.editingTenantId) {
        throw new Error("Selecciona un cliente para editar");
      }
      const payload = { name, description, active };
      response = await fetch(`${BACKEND_HTTP}/tenants/${encodeURIComponent(state.editingTenantId)}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + state.token,
        },
        body: JSON.stringify(payload),
      });
    }
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(detail || orFallback(response.status));
    }
    await loadTenants(true);
    if (mode === "create") {
      resetTenantForm("create");
      setTenantStatus("Cliente creado", "success");
    } else {
      setTenantStatus("Cliente actualizado", "success");
    }
  } catch (error) {
    console.error("submitTenantForm", error);
    setTenantStatus("Operacion fallida: " + ((error && error.message) || error), "error");
  }
}

function handleTenantListClick(event) {
  const target = event.target.closest('button[data-action]');
  if (!target) return;
  const empresaId = target.dataset.empresa || "";
  if (!empresaId) return;
  if (target.dataset.action === "switch") {
    selectTenant(empresaId);
  } else if (target.dataset.action === "edit") {
    const tenant = (state.tenants || []).find((item) => item.empresaId === empresaId);
    if (tenant) {
      fillTenantForm(tenant);
    }
  }
}

function selectTenant(empresaId) {
  if (!empresaId) return;
  state.empresaId = empresaId;
  setDirty(false);
  loadConfig(true, empresaId).catch((err) => {
    console.error("selectTenant", err);
    setStatus("No se pudo cambiar de empresa: " + ((err && err.message) || err), "error");
  });
}


async function saveConfig() {
  if (!state.canEdit) {
    setStatus("No tienes permisos para guardar.", "warning");
    return;
  }
  try {
    const prepared = prepareConfigForSave();
    const empresaId = state.isMaster && state.empresaId ? state.empresaId : null;
    const query = empresaId ? `?empresaId=${encodeURIComponent(empresaId)}` : "";
    const response = await fetch(BACKEND_HTTP + "/config" + query, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + state.token,
      },
      body: JSON.stringify(prepared),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail && detail.detail ? detail.detail : orFallback(response.status));
    }
    setDirty(false);
    setStatus("Configuracion guardada correctamente.", "success");
  } catch (error) {
    console.error("saveConfig", error);
    setStatus("No se pudo guardar: " + ((error && error.message) || error), "error");
  }
}
function prepareConfigForSave() {
  const cloneConfig = clone(state.config);
  cloneConfig.empresaId = state.empresaId || cloneConfig.empresaId || "";
  cloneConfig.roles = {
    admins: splitLines(dom.rolesAdmins?.value),
    operators: splitLines(dom.rolesOperators?.value),
    viewers: splitLines(dom.rolesViewers?.value),
  };
  cloneConfig.containers = (cloneConfig.containers || []).map((container) => {
    const cleanContainer = {
      title: container.title || "",
      objects: [],
    };
    if (Array.isArray(container.objects)) {
      cleanContainer.objects = container.objects.map((object) => sanitizeObject(object));
    }
    return cleanContainer;
  });
  return cloneConfig;
}
function sanitizeObject(object) {
  if (!object || typeof object !== "object") {
    return {};
  }
  const typeKey = normalizeType(object.type);
  const isKnown = OBJECT_TYPE_MAP.has(typeKey);
  if (!isKnown) {
    const rawClone = clone(object);
    if (typeof rawClone.label === "string") {
      rawClone.label = rawClone.label.trim();
    }
    if (typeof rawClone.topic === "string") {
      rawClone.topic = rawClone.topic.trim();
    }
    return rawClone;
  }
  const meta = resolveObjectMeta(object.type);
  const clean = {};
  clean.type = meta.value || object.type;
  meta.fields.forEach((field) => {
    if (field.type === "number") {
      const value = parseNumber(object[field.key]);
      if (value !== null) {
        clean[field.key] = value;
      }
    } else if (field.type === "color") {
      const value = ensureColor(object[field.key]);
      if (value) {
        clean[field.key] = value;
      }
    } else {
      const value = object[field.key];
      if (value !== undefined && value !== null && String(value).trim() !== "") {
        clean[field.key] = typeof value === "string" ? value.trim() : value;
      }
    }
  });
  if (!clean.label && object.label) {
    clean.label = String(object.label).trim();
  }
  if (!clean.topic && object.topic) {
    clean.topic = String(object.topic).trim();
  }
  if (object.payload && !clean.payload) {
    clean.payload = String(object.payload);
  }
  if (object.onColor && !clean.onColor) {
    clean.onColor = ensureColor(object.onColor);
  }
  if (object.offColor && !clean.offColor) {
    clean.offColor = ensureColor(object.offColor);
  }
  return clean;
}
function downloadConfig() {
  const prepared = prepareConfigForSave();
  const text = JSON.stringify(prepared, null, 2);
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const empresaSlug = (state.empresaId || "config").replace(/[^A-Za-z0-9_-]+/g, "_") || "config";
  link.download = `${empresaSlug}_scada_config.json`;
  link.click();
  URL.revokeObjectURL(url);
  setStatus("Archivo descargado.", "success");
}
















