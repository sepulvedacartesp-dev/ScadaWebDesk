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
const MAX_WIDGETS_PER_CONTAINER = 6;

const state = {
  token: null,
  empresaId: null,
  claimEmpresaId: null,
  role: "viewer",
  isMaster: false,
  canEdit: false,
  canManageUsers: false,
  dirty: false,
  tenants: [],
  tenantsLoaded: false,
  tenantLoading: false,
  editingTenantId: null,
  users: [],
  usersLoaded: false,
  userLoading: false,
  userFallback: false,
  showingUserForm: false,
  userInviteLink: null,
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
  userCard: document.getElementById("user-card"),
  toggleUserForm: document.getElementById("toggle-user-form"),
  refreshUsersBtn: document.getElementById("refresh-users-btn"),
  userForm: document.getElementById("user-form"),
  userEmail: document.getElementById("user-email"),
  userRole: document.getElementById("user-role"),
  userSendInvite: document.getElementById("user-send-invite"),
  userFormStatus: document.getElementById("user-form-status"),
  userSubmitBtn: document.getElementById("user-submit-btn"),
  cancelUserForm: document.getElementById("cancel-user-form"),
  userStatus: document.getElementById("user-status"),
  userList: document.getElementById("user-list"),
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

let containerUiState = new WeakMap();
let objectUiState = new WeakMap();


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
  dom.toggleUserForm?.addEventListener("click", () => toggleUserForm());
  dom.cancelUserForm?.addEventListener("click", () => toggleUserForm(false));
  dom.userForm?.addEventListener("submit", submitUserForm);
  dom.userList?.addEventListener("click", handleUserListClick);
  dom.refreshUsersBtn?.addEventListener("click", () => loadUsers(true));
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
    state.canManageUsers = false;
    state.users = [];
    state.usersLoaded = false;
    state.userLoading = false;
    state.userFallback = false;
    state.showingUserForm = false;
    state.userInviteLink = null;
    ensureUserCardVisibility();
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
    state.canManageUsers = false;
    state.users = [];
    state.usersLoaded = false;
    state.userLoading = false;
    state.userFallback = false;
    state.showingUserForm = false;
    state.userInviteLink = null;
    containerUiState = new WeakMap();
    objectUiState = new WeakMap();
    setDirty(false);
    updateRoleBadge();
    applyPermissions();
    renderAll();
    renderMasterPanel();
    ensureUserCardVisibility();
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
    const previousEmpresaId = state.empresaId;
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
    const resolvedEmpresaId = (payload.empresaId || config.empresaId || empresaId || state.empresaId || "").toString().trim();
    state.empresaId = resolvedEmpresaId ? resolvedEmpresaId.toLowerCase() : "";
    const empresaChanged = previousEmpresaId !== state.empresaId;
    state.role = payload.role || determineRole(config, user.email);
    state.canEdit = state.role === "admin";
    state.canManageUsers = state.isMaster || state.role === "admin";
    if (empresaChanged) {
      state.users = [];
      state.usersLoaded = false;
      state.userLoading = false;
      state.userFallback = false;
      state.showingUserForm = false;
      state.userInviteLink = null;
    }
    state.config = config;
    state.config.empresaId = state.empresaId;
    containerUiState = new WeakMap();
    objectUiState = new WeakMap();
    setDirty(false);
    updateRoleBadge();
    applyPermissions();
    renderAll();
    ensureUserCardVisibility();
    if (state.canManageUsers && (empresaChanged || !state.usersLoaded)) {
      loadUsers(true).catch((error) => console.error("loadUsers", error));
    }
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


function determineRole(config, email) {
  if (!config || typeof config !== "object" || !email) return "operador";
  const roles = config.roles || {};
  const lowerEmail = String(email).trim().toLowerCase();
  if (emailsFrom(roles.admins).includes(lowerEmail)) return "admin";
  if (emailsFrom(roles.operators).includes(lowerEmail)) return "operador";
  if (emailsFrom(roles.viewers).includes(lowerEmail)) return "visualizacion";
  return "operador";
}

function emailsFrom(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim().toLowerCase()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(/[\r\n,;]+/)
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean);
  }
  return [];
}

function renderAll() {
  renderGeneralSection();
  renderRolesSection();
  renderContainers();
  renderUserList();
}

function renderGeneralSection() {
  if (dom.mainTitle) {
    dom.mainTitle.value = state.config.mainTitle || "";
    dom.mainTitle.disabled = !state.canEdit;
  }
}

function renderRolesSection() {
  const roles = state.config.roles || {};
  if (dom.rolesAdmins) {
    dom.rolesAdmins.value = (roles.admins || []).join("\n");
    dom.rolesAdmins.disabled = !state.canEdit;
  }
  if (dom.rolesOperators) {
    dom.rolesOperators.value = (roles.operators || []).join("\n");
    dom.rolesOperators.disabled = !state.canEdit;
  }
  if (dom.rolesViewers) {
    dom.rolesViewers.value = (roles.viewers || []).join("\n");
    dom.rolesViewers.disabled = !state.canEdit;
  }
}



function renderContainers() {
  if (!dom.containersList || !dom.containerTemplate) return;
  dom.containersList.querySelectorAll('[data-container-index]').forEach((node) => node.remove());
  const containers = Array.isArray(state.config.containers) ? state.config.containers : [];
  const hasContainers = containers.length > 0;
  if (dom.containersEmpty) {
    dom.containersEmpty.hidden = hasContainers;
  }
  containers.forEach((container, index) => {
    ensureContainerUiState(container);
    const card = dom.containerTemplate.content.firstElementChild.cloneNode(true);
    card.dataset.containerIndex = String(index);
    const titleInput = card.querySelector('[data-field="title"]');
    const heading = card.querySelector('.container-title');
    if (titleInput) {
      titleInput.value = container.title || "";
      titleInput.disabled = !state.canEdit;
      titleInput.addEventListener('input', (event) => {
        const value = event.target.value || "";
        state.config.containers[index].title = value;
        heading.textContent = formatContainerTitle(value, index);
        setDirty(true);
      });
    }
    heading.textContent = formatContainerTitle(container.title, index);
    const collapsed = isContainerCollapsed(container);
    card.classList.toggle('collapsed', collapsed);
    updateContainerToggleState(card, collapsed);
    updateContainerSummary(card, container);
    renderObjects(card, container, index);
    const editableButtons = card.querySelectorAll('.btn-editable');
    editableButtons.forEach((btn) => {
      if (!state.canEdit) {
        btn.setAttribute('disabled', '');
      } else {
        btn.removeAttribute('disabled');
      }
    });
    applyContainerCapacityState(card, container);
    dom.containersList.appendChild(card);
  });
  updateExpandCollapseButton();
}

function ensureContainerUiState(container) {
  if (!container || typeof container !== "object") return;
  if (!containerUiState.has(container)) {
    containerUiState.set(container, { collapsed: false });
  }
}

function isContainerCollapsed(container) {
  const entry = containerUiState.get(container);
  return !!(entry && entry.collapsed);
}

function setContainerCollapsed(container, collapsed) {
  if (!container || typeof container !== "object") return;
  const entry = containerUiState.get(container) || {};
  entry.collapsed = !!collapsed;
  containerUiState.set(container, entry);
}

function updateContainerToggleState(card, collapsed) {
  if (!card) return;
  const toggleBtn = card.querySelector('[data-action="toggle-collapse"]');
  if (!toggleBtn) return;
  toggleBtn.setAttribute('aria-expanded', String(!collapsed));
  toggleBtn.textContent = collapsed ? 'Expandir' : 'Contraer';
}

function ensureObjectUiState(object) {
  if (!object || typeof object !== 'object') return;
  if (!objectUiState.has(object)) {
    objectUiState.set(object, { collapsed: false });
  }
}

function isObjectCollapsed(object) {
  const entry = objectUiState.get(object);
  return !!(entry && entry.collapsed);
}

function setObjectCollapsed(object, collapsed) {
  if (!object || typeof object !== 'object') return;
  const entry = objectUiState.get(object) || {};
  entry.collapsed = !!collapsed;
  objectUiState.set(object, entry);
}

function updateObjectToggleState(card, collapsed) {
  if (!card) return;
  const toggleBtn = card.querySelector('[data-action="toggle-object-collapse"]');
  if (!toggleBtn) return;
  toggleBtn.setAttribute('aria-expanded', String(!collapsed));
  toggleBtn.textContent = collapsed ? 'Expandir' : 'Contraer';
}

function formatContainerTitle(title, index) {
  const base = title && title.trim() ? title.trim() : `Contenedor ${index + 1}`;
  return base;
}

function renderObjects(card, container, containerIndex) {
  const wrapper = card.querySelector('.objects-wrap');
  if (!wrapper || !dom.objectTemplate) return;
  wrapper.textContent = '';
  const objects = Array.isArray(container.objects) ? container.objects : [];
  if (!objects.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'Sin widgets. Usa "Agregar widget".';
    wrapper.appendChild(empty);
    return;
  }
  objects.forEach((object, objectIndex) => {
    const objCard = dom.objectTemplate.content.firstElementChild.cloneNode(true);
    objCard.dataset.objectIndex = String(objectIndex);
    const header = objCard.querySelector('.object-header h4');
    const toolbar = objCard.querySelector('.object-toolbar');
    const fieldsHost = objCard.querySelector('.object-fields');
    const advancedHost = objCard.querySelector('.object-advanced-fields');
    const advancedWrapper = objCard.querySelector('[data-advanced="wrapper"]');
    const meta = resolveObjectMeta(object.type);
    const labelPreview = object.label && object.label.trim() ? object.label.trim() : `Widget ${objectIndex + 1}`;
    ensureObjectUiState(object);
    const collapsed = isObjectCollapsed(object);
    objCard.classList.toggle('collapsed', collapsed);
    updateObjectToggleState(objCard, collapsed);
    if (advancedWrapper && collapsed && typeof advancedWrapper.open === 'boolean') {
      advancedWrapper.open = false;
    }
    if (header) {
      header.textContent = `${labelPreview} - ${meta.label}`;
    }
    if (!state.canEdit && toolbar) {
      toolbar.querySelectorAll('button').forEach((btn) => btn.setAttribute('disabled', ''));
    }
    buildPrimaryFields(fieldsHost, meta, object, containerIndex, objectIndex);
    const advancedFields = meta.fields.filter((item) => item.section === 'advanced');
    if (advancedWrapper) {
      if (advancedFields.length) {
        advancedWrapper.style.display = 'block';
        buildAdvancedFields(advancedHost, advancedFields, object, containerIndex, objectIndex);
      } else {
        advancedWrapper.style.display = 'none';
      }
    }
    wrapper.appendChild(objCard);
  });
}

function buildPrimaryFields(host, meta, object, containerIndex, objectIndex) {
  if (!host) return;
  host.textContent = '';
  const typeGroup = document.createElement('div');
  typeGroup.className = 'form-group';
  const typeLabel = document.createElement('label');
  typeLabel.textContent = 'Tipo de widget';
  typeGroup.appendChild(typeLabel);
  const typeSelect = document.createElement('select');
  typeSelect.className = 'select-input';
  OBJECT_TYPES.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.value;
    option.textContent = item.label;
    option.dataset.hint = item.hint;
    typeSelect.appendChild(option);
  });
  const currentType = normalizeType(object.type);
  if (!OBJECT_TYPE_MAP.has(currentType)) {
    const customOption = document.createElement('option');
    customOption.value = object.type || '';
    customOption.textContent = object.type ? `Personalizado (${object.type})` : 'Tipo no definido';
    typeSelect.appendChild(customOption);
  }
  typeSelect.value = object.type || meta.value;
  typeSelect.disabled = !state.canEdit;
  typeSelect.addEventListener('change', (event) => {
    updateObjectType(containerIndex, objectIndex, event.target.value);
  });
  typeGroup.appendChild(typeSelect);
  if (meta.hint) {
    const hint = document.createElement('p');
    hint.className = 'helper-text';
    hint.textContent = meta.hint;
    typeGroup.appendChild(hint);
  }
  host.appendChild(typeGroup);
  meta.fields
    .filter((item) => item.section !== 'advanced')
    .forEach((field) => {
      host.appendChild(
        createFieldElement(field, object[field.key], (value) => {
          updateObjectField(containerIndex, objectIndex, field, value);
        })
      );
    });
}

function buildAdvancedFields(host, fields, object, containerIndex, objectIndex) {
  if (!host) return;
  host.textContent = '';
  fields.forEach((field) => {
    host.appendChild(
      createFieldElement(field, object[field.key], (value) => {
        updateObjectField(containerIndex, objectIndex, field, value);
      })
    );
  });
}

function createFieldElement(field, currentValue, onChange) {
  const group = document.createElement('div');
  group.className = 'form-group';
  const label = document.createElement('label');
  label.textContent = field.label || field.key;
  group.appendChild(label);
  let input;
  if (field.type === 'color') {
    const wrapper = document.createElement('div');
    wrapper.className = 'object-color-input';
    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    colorInput.value = ensureColor(currentValue);
    colorInput.disabled = !state.canEdit;
    const textInput = document.createElement('input');
    textInput.type = 'text';
    textInput.className = 'text-input';
    textInput.placeholder = field.placeholder || '#00b4d8';
    textInput.value = ensureColor(currentValue);
    textInput.disabled = !state.canEdit;
    colorInput.addEventListener('input', (event) => {
      const value = event.target.value;
      onChange(value);
      textInput.value = value;
      setDirty(true);
    });
    textInput.addEventListener('change', (event) => {
      const value = ensureColor(event.target.value);
      event.target.value = value;
      colorInput.value = value;
      onChange(value);
      setDirty(true);
    });
    wrapper.append(colorInput, textInput);
    input = wrapper;
  } else {
    const element = document.createElement('input');
    element.className = field.type === 'number' ? 'number-input' : 'text-input';
    element.type = field.type === 'number' ? 'number' : 'text';
    if (field.placeholder) {
      element.placeholder = field.placeholder;
    }
    if (field.type === 'number' && typeof currentValue === 'number') {
      element.value = String(currentValue);
    } else {
      element.value = currentValue !== undefined && currentValue !== null ? String(currentValue) : '';
    }
    element.disabled = !state.canEdit;
    element.addEventListener('change', (event) => {
      const value = field.type === 'number' ? parseNumber(event.target.value) : event.target.value;
      onChange(value);
      setDirty(true);
    });
    input = element;
  }
  group.appendChild(input);
  return group;
}

function updateObjectField(containerIndex, objectIndex, field, value) {
  const container = state.config.containers?.[containerIndex];
  if (!container) return;
  const object = container.objects?.[objectIndex];
  if (!object) return;
  if (field.type === 'number') {
    if (value === null || value === '' || Number.isNaN(value)) {
      delete object[field.key];
    } else {
      object[field.key] = value;
    }
  } else {
    object[field.key] = value === undefined ? '' : value;
  }
  const cardElement = dom.containersList?.querySelector(`[
    data-container-index="${containerIndex}"] [data-object-index="${objectIndex}"]
  `);
  if (cardElement) {
    const header = cardElement.querySelector('.object-header h4');
    if (header) {
      const meta = resolveObjectMeta(object.type);
      const labelPreview = object.label && object.label.trim() ? object.label.trim() : `Widget ${objectIndex + 1}`;
      header.textContent = `${labelPreview} - ${meta.label}`;
    }
  }
  updateContainerSummary(dom.containersList?.querySelector(`[data-container-index="${containerIndex}"]`), container);
  setDirty(true);
}

function updateObjectType(containerIndex, objectIndex, nextType) {
  const container = state.config.containers?.[containerIndex];
  if (!container) return;
  const current = container.objects?.[objectIndex];
  if (!current) return;
  const meta = resolveObjectMeta(nextType);
  const template = clone(meta.defaults || { type: nextType });
  const preservedLabel = current.label;
  const preservedTopic = current.topic;
  container.objects[objectIndex] = Object.assign({}, template, {
    label: preservedLabel,
    topic: preservedTopic,
    type: meta.value,
  });
  setDirty(true);
  renderContainers();
}

function resolveObjectMeta(type) {
  const key = normalizeType(type);
  if (OBJECT_TYPE_MAP.has(key)) {
    return OBJECT_TYPE_MAP.get(key);
  }
  return {
    value: type || '',
    label: type ? `Tipo ${type}` : 'Tipo no definido',
    hint: 'Este tipo no esta mapeado, los cambios se guardaran tal cual.',
    defaults: { type: type || '' },
    fields: [
      { key: 'label', label: 'Nombre visible', type: 'text', placeholder: 'Widget', section: 'primary' },
      { key: 'topic', label: 'Topic MQTT', type: 'text', placeholder: 'planta/tag', section: 'primary' },
    ],
  };
}

function ensureColor(value) {
  const defaultColor = '#00b4d8';
  if (!value) return defaultColor;
  const hex = String(value).trim();
  if (/^#[0-9a-fA-F]{6}$/.test(hex)) {
    return hex.toLowerCase();
  }
  return defaultColor;
}

function updateRolesFromInputs() {
  state.config.roles = {
    admins: splitLines(dom.rolesAdmins?.value),
    operators: splitLines(dom.rolesOperators?.value),
    viewers: splitLines(dom.rolesViewers?.value),
  };
  setDirty(true);
}

function splitLines(value) {
  if (value === undefined || value === null) return [];
  return String(value)
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}



function addContainer() {
  const container = { title: '', objects: [] };
  if (!Array.isArray(state.config.containers)) {
    state.config.containers = [];
  }
  state.config.containers.push(container);
  setDirty(true);
  renderContainers();
}

function handleContainerActions(event) {
  const actionBtn = event.target.closest('[data-action]');
  if (!actionBtn) return;
  const card = actionBtn.closest('[data-container-index]');
  if (!card) return;
  const containerIndex = Number(card.dataset.containerIndex || '0');
  const action = actionBtn.dataset.action;
  if (action === 'toggle-collapse') {
    const container = state.config.containers?.[containerIndex];
    if (!container) return;
    const shouldCollapse = !card.classList.contains('collapsed');
    setContainerCollapsed(container, shouldCollapse);
    card.classList.toggle('collapsed', shouldCollapse);
    updateContainerToggleState(card, shouldCollapse);
    updateExpandCollapseButton();
    return;
  }
  if (action === 'toggle-object-collapse') {
    const container = state.config.containers?.[containerIndex];
    if (!container) return;
    const objectCard = actionBtn.closest('[data-object-index]');
    if (!objectCard) return;
    const objectIndex = Number(objectCard.dataset.objectIndex || '0');
    const targetObject = container.objects?.[objectIndex];
    if (!targetObject) return;
    const shouldCollapse = !objectCard.classList.contains('collapsed');
    setObjectCollapsed(targetObject, shouldCollapse);
    objectCard.classList.toggle('collapsed', shouldCollapse);
    updateObjectToggleState(objectCard, shouldCollapse);
    const advancedWrapper = objectCard.querySelector('[data-advanced="wrapper"]');
    if (shouldCollapse && advancedWrapper && typeof advancedWrapper.open === 'boolean') {
      advancedWrapper.open = false;
    }
    return;
  }
  if (!state.canEdit) return;
  if (action === 'add-object') {
    addObject(containerIndex);
  } else if (action === 'remove-container') {
    removeContainer(containerIndex);
  } else if (action === 'duplicate-container') {
    duplicateContainer(containerIndex);
  } else if (action === 'remove-object') {
    const objectCard = actionBtn.closest('[data-object-index]');
    if (objectCard) {
      removeObject(containerIndex, Number(objectCard.dataset.objectIndex || '0'));
    }
  } else if (action === 'duplicate-object') {
    const objectCard = actionBtn.closest('[data-object-index]');
    if (objectCard) {
      duplicateObject(containerIndex, Number(objectCard.dataset.objectIndex || '0'));
    }
  }
}

function addObject(containerIndex, type = 'level') {
  const container = state.config.containers?.[containerIndex];
  if (!container) return;
  container.objects = Array.isArray(container.objects) ? container.objects : [];
  if (!containerHasCapacity(container)) {
    setStatus(`Cada contenedor admite un maximo de ${MAX_WIDGETS_PER_CONTAINER} widgets.`, 'warning');
    return;
  }
  const meta = resolveObjectMeta(type);
  const object = clone(meta.defaults || { type });
  container.objects.push(object);
  setDirty(true);
  renderContainers();
}

function removeContainer(containerIndex) {
  const container = state.config.containers?.[containerIndex];
  if (!container) return;
  if (!window.confirm('Eliminar contenedor y todos sus widgets?')) return;
  state.config.containers.splice(containerIndex, 1);
  setDirty(true);
  renderContainers();
}

function duplicateContainer(containerIndex) {
  const container = state.config.containers?.[containerIndex];
  if (!container) return;
  state.config.containers.splice(containerIndex + 1, 0, clone(container));
  setDirty(true);
  renderContainers();
}

function removeObject(containerIndex, objectIndex) {
  const container = state.config.containers?.[containerIndex];
  if (!container) return;
  if (!window.confirm('Eliminar este widget?')) return;
  container.objects.splice(objectIndex, 1);
  setDirty(true);
  renderContainers();
}

function duplicateObject(containerIndex, objectIndex) {
  const container = state.config.containers?.[containerIndex];
  if (!container) return;
  container.objects = Array.isArray(container.objects) ? container.objects : [];
  if (!containerHasCapacity(container)) {
    setStatus(`Cada contenedor admite un maximo de ${MAX_WIDGETS_PER_CONTAINER} widgets.`, 'warning');
    return;
  }
  const object = container.objects?.[objectIndex];
  if (!object) return;
  container.objects.splice(objectIndex + 1, 0, clone(object));
  setDirty(true);
  renderContainers();
}

function toggleAllContainers() {
  const containers = Array.isArray(state.config.containers) ? state.config.containers : [];
  if (!containers.length) {
    updateExpandCollapseButton();
    return;
  }
  const allExpanded = containers.every((container) => !isContainerCollapsed(container));
  const collapseAll = allExpanded;
  containers.forEach((container) => {
    setContainerCollapsed(container, collapseAll);
  });
  const cards = dom.containersList?.querySelectorAll('[data-container-index]') || [];
  cards.forEach((card, index) => {
    card.classList.toggle('collapsed', collapseAll);
    updateContainerToggleState(card, collapseAll);
    updateContainerSummary(card, state.config.containers[index]);
  });
  updateExpandCollapseButton();
}

function updateExpandCollapseButton() {
  if (!dom.expandCollapse) return;
  const containers = Array.isArray(state.config.containers) ? state.config.containers : [];
  const total = containers.length;
  const allExpanded = total === 0 || containers.every((container) => !isContainerCollapsed(container));
  dom.expandCollapse.dataset.expanded = String(allExpanded);
  dom.expandCollapse.textContent = allExpanded ? 'Contraer todo' : 'Expandir todo';
  dom.expandCollapse.disabled = total === 0;
}

function updateContainerSummary(card, container) {
  if (!card || !container) return;
  const summaryWidgets = card.querySelector('[data-summary="widgets"]');
  const summaryTopics = card.querySelector('[data-summary="topics"]');
  const widgets = Array.isArray(container.objects) ? container.objects.length : 0;
  const topics = new Set((container.objects || []).map((obj) => (obj.topic || '').trim()).filter(Boolean));
  if (summaryWidgets) {
    summaryWidgets.textContent = widgets === 1 ? '1 widget' : `${widgets} widgets`;
  }
  if (summaryTopics) {
    summaryTopics.textContent = topics.size === 1 ? '1 topic' : `${topics.size} topics`;
  }
}

function containerHasCapacity(container) {
  const objects = Array.isArray(container?.objects) ? container.objects : [];
  return objects.length < MAX_WIDGETS_PER_CONTAINER;
}

function applyContainerCapacityState(card, container) {
  if (!card || !container) return;
  const hasCapacity = containerHasCapacity(container);
  const addBtn = card.querySelector('[data-action="add-object"]');
  if (addBtn) {
    if (!state.canEdit || !hasCapacity) {
      addBtn.setAttribute('disabled', '');
    } else {
      addBtn.removeAttribute('disabled');
    }
  }
  const capacityMessage = card.querySelector('[data-capacity-message]');
  if (capacityMessage) {
    capacityMessage.hidden = hasCapacity;
  }
  const duplicateButtons = card.querySelectorAll('[data-action="duplicate-object"]');
  duplicateButtons.forEach((btn) => {
    if (!state.canEdit || !hasCapacity) {
      btn.setAttribute('disabled', '');
    } else {
      btn.removeAttribute('disabled');
    }
  });
}

function setDirty(isDirty) {
  state.dirty = !!isDirty;
  if (state.dirty) {
    setStatus('Tienes cambios sin guardar.', 'warning');
  }
}

function applyPermissions() {
  const canEdit = Boolean(state.canEdit);
  dom.root?.classList.toggle('readonly', !canEdit);
  if (typeof document !== 'undefined') {
    document.body?.classList.toggle('readonly', !canEdit);
  }
  const editableButtons = [dom.saveBtn, dom.importBtn, dom.downloadBtn, dom.addContainer, dom.expandCollapse];
  editableButtons.forEach((element) => {
    if (!element) return;
    if (canEdit) {
      element.removeAttribute('disabled');
    } else {
      element.setAttribute('disabled', '');
    }
  });
  dom.containersList?.classList.toggle('is-readonly', !canEdit);
  if (!state.isMaster) {
    dom.refreshTenantsBtn?.setAttribute('disabled', '');
    dom.resetTenantFormBtn?.setAttribute('disabled', '');
    dom.tenantSubmit?.setAttribute('disabled', '');
  } else {
    dom.refreshTenantsBtn?.removeAttribute('disabled');
    dom.resetTenantFormBtn?.removeAttribute('disabled');
    dom.tenantSubmit?.removeAttribute('disabled');
  }
  if (!state.canManageUsers) {
    dom.toggleUserForm?.setAttribute('disabled', '');
    dom.refreshUsersBtn?.setAttribute('disabled', '');
    dom.userSubmitBtn?.setAttribute('disabled', '');
    toggleUserForm(false);
  } else {
    dom.toggleUserForm?.removeAttribute('disabled');
    dom.refreshUsersBtn?.removeAttribute('disabled');
    dom.userSubmitBtn?.removeAttribute('disabled');
  }
}

function updateRoleBadge() {
  if (!dom.roleBadge) return;
  const baseRole = state.isMaster ? 'MASTER' : (state.role || 'VIEWER').toUpperCase();
  dom.roleBadge.textContent = state.empresaId ? `${baseRole} - ${state.empresaId}` : baseRole;
}

function parseNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function clone(value) {
  if (typeof structuredClone === 'function') {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function normalizeType(type) {
  return String(type || '').toLowerCase();
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
      objectUiState = new WeakMap();
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

function formatUserRole(role) {
  switch (String(role || "").toLowerCase()) {
    case "admin":
      return "Administrador";
    case "visualizacion":
      return "Solo lectura";
    case "operador":
    default:
      return "Operador";
  }
}

function formatTimestamp(value) {
  if (!value) return "Nunca";
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  } catch (error) {
    return value;
  }
}

function setUserStatus(message = "", tone = "info") {
  if (!dom.userStatus) return;
  dom.userStatus.textContent = message || "";
  dom.userStatus.dataset.tone = tone || "info";
}

function setUserFormStatus(message = "", tone = "info") {
  if (!dom.userFormStatus) return;
  dom.userFormStatus.textContent = message || "";
  dom.userFormStatus.dataset.tone = tone || "info";
}

function resetUserForm() {
  if (!dom.userForm) return;
  dom.userForm.reset();
  if (dom.userSendInvite) {
    dom.userSendInvite.checked = true;
  }
  setUserFormStatus("");
}

function toggleUserForm(force) {
  if (!dom.userForm || !dom.toggleUserForm) return;
  const shouldShow = typeof force === "boolean" ? force : !state.showingUserForm;
  state.showingUserForm = shouldShow;
  dom.userForm.hidden = !shouldShow;
  dom.toggleUserForm.textContent = shouldShow ? "Cerrar formulario" : "Agregar usuario";
  if (!shouldShow) {
    resetUserForm();
  } else if (dom.userEmail) {
    dom.userEmail.focus();
  }
}

function renderUserList() {
  if (!dom.userList) return;
  if (!state.canManageUsers) {
    dom.userList.innerHTML = "";
    return;
  }
  const users = Array.isArray(state.users) ? state.users : [];
  if (!users.length) {
    dom.userList.innerHTML = '<li class="user-item user-item--empty"><div class="user-item__header"><h4 class="user-item__title">Sin usuarios registrados</h4></div><div class="user-item__meta">Crea un usuario nuevo para enviar invitaciones de acceso.</div></li>';
    return;
  }
  const currentUid = (firebase.auth().currentUser && firebase.auth().currentUser.uid) || null;
  dom.userList.innerHTML = users
    .map((user) => {
      const email = escapeHtml(user.email || "");
      const role = escapeHtml(formatUserRole(user.role));
      const lastLogin = user.lastLoginAt ? `Ultimo ingreso: ${escapeHtml(formatTimestamp(user.lastLoginAt))}` : "Sin ingresos";
      const createdAt = user.createdAt ? `Alta: ${escapeHtml(formatTimestamp(user.createdAt))}` : "";
      const statusBits = [];
      if (user.emailVerified) statusBits.push("Verificado");
      if (user.isMasterAdmin) statusBits.push("Master");
      if (user.disabled) statusBits.push("Deshabilitado");
      const status = statusBits.length ? statusBits.join(" | ") : "Activo";
      const hasUid = Boolean(user.uid);
      const uid = hasUid ? escapeHtml(String(user.uid)) : "";
      const isSelf = hasUid && currentUid && user.uid === currentUid;
      const inviteLabel = user.lastLoginAt ? "Reenviar enlace" : "Enviar invitacion";
      const actions = hasUid
        ? `<div class="user-item__actions">
          <button type="button" class="btn btn-link" data-action="invite" data-uid="${uid}" data-email="${email}">${inviteLabel}</button>
          <button type="button" class="btn btn-link btn-danger-light" data-action="delete" data-uid="${uid}" data-email="${email}" ${isSelf ? "disabled" : ""}>Eliminar</button>
        </div>`
        : '<div class="user-item__note">Gestion disponible solo para usuarios registrados mediante Firebase Admin.</div>';
      return `
      <li class="user-item"${hasUid ? ` data-uid="${uid}"` : ""}>
        <div class="user-item__header">
          <h4 class="user-item__title">${email}</h4>
          <span class="user-item__badge">${role}</span>
        </div>
        <div class="user-item__meta">${escapeHtml(status)}</div>
        <div class="user-item__meta">${escapeHtml(lastLogin)}</div>
        ${createdAt ? `<div class="user-item__meta">${escapeHtml(createdAt)}</div>` : ""}
        ${actions}
      </li>`;
    })
    .join("");
}

async function loadUsers(force = false) {
  if (!state.canManageUsers || !state.empresaId) return;
  if (!force && (state.usersLoaded || state.userLoading)) return;
  if (state.userLoading) return;
  state.userLoading = true;
  setUserStatus("Cargando usuarios...", "info");
  dom.refreshUsersBtn?.setAttribute("disabled", "");
  try {
    const query = `?empresaId=${encodeURIComponent(state.empresaId)}`;
    const response = await fetch(`${BACKEND_HTTP}/users${query}`, {
      headers: { Authorization: "Bearer " + state.token },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || orFallback(response.status));
    }
    const payload = await response.json();
    state.users = Array.isArray(payload.users) ? payload.users : [];
    state.usersLoaded = true;
    state.userFallback = Boolean(payload.fallback) || state.users.some((item) => !item?.uid);
    renderUserList();
    if (state.userFallback) {
      const message = payload.message || "No se pudo obtener el detalle completo desde Firebase. Se muestran los correos definidos en la configuracion.";
      setUserStatus(message, "warning");
    } else {
      setUserStatus(`Usuarios actualizados (${state.users.length})`, "success");
    }
  } catch (error) {
    console.error("loadUsers", error);
    setUserStatus("No se pudo cargar la lista: " + ((error && error.message) || error), "error");
  } finally {
    state.userLoading = false;
    if (state.canManageUsers) {
      dom.refreshUsersBtn?.removeAttribute("disabled");
    }
  }
}

async function submitUserForm(event) {
  event.preventDefault();
  if (!state.canManageUsers || !state.empresaId) {
    setUserFormStatus("No tienes permisos para crear usuarios", "error");
    return;
  }
  const email = dom.userEmail?.value.trim();
  const role = dom.userRole?.value || "operador";
  const sendInvite = Boolean(dom.userSendInvite?.checked);
  if (!email) {
    setUserFormStatus("Ingresa un email valido", "warning");
    dom.userEmail?.focus();
    return;
  }
  dom.userSubmitBtn?.setAttribute("disabled", "");
  setUserFormStatus("Creando usuario...", "info");
  try {
    const payload = {
      email,
      role,
      sendInvite,
      empresaId: state.empresaId,
    };
    const response = await fetch(`${BACKEND_HTTP}/users`, {
      method: "POST",
      headers: {
        Authorization: "Bearer " + state.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || orFallback(response.status));
    }
    const data = await response.json();
    toggleUserForm(false);
    await loadUsers(true);
    if (data.resetLink) {
      state.userInviteLink = data.resetLink;
      setUserStatus("Usuario creado. Enlace listo para compartir.", data.inviteSent ? "success" : "info");
    } else {
      setUserStatus("Usuario creado correctamente.", "success");
    }
  } catch (error) {
    console.error("submitUserForm", error);
    setUserFormStatus("No se pudo crear: " + ((error && error.message) || error), "error");
  } finally {
    dom.userSubmitBtn?.removeAttribute("disabled");
  }
}

async function handleUserListClick(event) {
  const button = event.target?.closest?.("button[data-action]");
  if (!button || !state.canManageUsers || !state.empresaId) return;
  const action = button.dataset.action;
  const uid = button.dataset.uid;
  const email = button.dataset.email || "";
  if (!uid) return;
  if (action === "delete") {
    const confirmDelete = window.confirm(`Eliminar el usuario ${email}?`);
    if (!confirmDelete) return;
    button.setAttribute("disabled", "");
    setUserStatus("Eliminando usuario...", "info");
    try {
      const query = `?empresaId=${encodeURIComponent(state.empresaId)}`;
      const response = await fetch(`${BACKEND_HTTP}/users/${encodeURIComponent(uid)}${query}`, {
        method: "DELETE",
        headers: { Authorization: "Bearer " + state.token },
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || orFallback(response.status));
      }
      state.users = (state.users || []).filter((item) => item.uid !== uid);
      renderUserList();
      setUserStatus(`Usuario ${email} eliminado`, "success");
    } catch (error) {
      console.error("deleteUser", error);
      setUserStatus("No se pudo eliminar: " + ((error && error.message) || error), "error");
    } finally {
      button.removeAttribute("disabled");
    }
    return;
  }
  if (action === "invite") {
    button.setAttribute("disabled", "");
    setUserStatus("Generando enlace de restablecimiento...", "info");
    try {
      const query = `?empresaId=${encodeURIComponent(state.empresaId)}`;
      const response = await fetch(`${BACKEND_HTTP}/users/${encodeURIComponent(uid)}/reset-link${query}`, {
        method: "POST",
        headers: {
          Authorization: "Bearer " + state.token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ sendEmail: true }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || orFallback(response.status));
      }
      const result = await response.json();
      state.userInviteLink = result.resetLink || null;
      const suffix = result.emailSent ? "Se envio un correo al usuario." : "Comparte el enlace manualmente.";
      setUserStatus(`Enlace generado. ${suffix}`, "success");
    } catch (error) {
      console.error("resetLink", error);
      setUserStatus("No se pudo generar el enlace: " + ((error && error.message) || error), "error");
    } finally {
      button.removeAttribute("disabled");
    }
  }
}

function ensureUserCardVisibility() {
  if (!dom.userCard) return;
  const allowed = state.canManageUsers && Boolean(state.empresaId);
  dom.userCard.hidden = !allowed;
  if (!allowed) {
    state.users = [];
    state.usersLoaded = false;
    state.userLoading = false;
    state.userFallback = false;
    state.showingUserForm = false;
    if (dom.userForm) {
      dom.userForm.hidden = true;
    }
    renderUserList();
    setUserStatus("");
    return;
  }
  renderUserList();
  if (!state.usersLoaded && !state.userLoading) {
    loadUsers().catch((error) => console.error("loadUsers", error));
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


















function setStatus(message, type = "info") {
  if (!dom.statusBanner) return;
  dom.statusBanner.textContent = message || "";
  dom.statusBanner.classList.remove("success", "error", "warning", "info");
  dom.statusBanner.classList.add(type || "info");
}
