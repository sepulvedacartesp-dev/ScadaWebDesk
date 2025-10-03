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
  role: "viewer",
  canEdit: false,
  dirty: false,
  expandAll: true,
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
};

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
}

async function onAuthStateChanged(user) {
  if (user) {
    dom.sessionStatus.textContent = "Sesion activa: " + user.email;
    dom.logoutBtn?.removeAttribute("disabled");
    dom.openLoginBtn?.setAttribute("disabled", "");
    await refreshToken(user);
    await loadConfig();
  } else {
    dom.sessionStatus.textContent = "Sin sesion";
    dom.logoutBtn?.setAttribute("disabled", "");
    dom.openLoginBtn?.removeAttribute("disabled");
    state.token = null;
    state.role = "viewer";
    state.canEdit = false;
    state.config = createEmptyConfig();
    setDirty(false);
    updateRoleBadge();
    applyPermissions();
    renderAll();
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

async function loadConfig(force = false) {
  const user = firebase.auth().currentUser;
  if (!user) return;
  try {
    if (!state.token || force) {
      await refreshToken(user);
    }
    setStatus("Cargando configuracion...", "info");
    const response = await fetch(BACKEND_HTTP + "/config", {
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
    state.role = payload.role || determineRole(config, user.email);
    state.canEdit = state.role === "admin";
    state.config = config;
    setDirty(false);
    updateRoleBadge();
    applyPermissions();
    renderAll();
    setStatus(state.canEdit ? "Configuracion cargada. Puedes editar." : "Configuracion cargada en modo lectura.", state.canEdit ? "success" : "info");
  } catch (error) {
    console.error("loadConfig", error);
    setStatus("Error al cargar: " + ((error && error.message) || error), "error");
  }
}

function determineRole(config, email) {
  if (!email || !config || typeof config !== "object") return "operador";
  const roles = config.roles || {};
  const lowerEmail = email.toLowerCase();
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
    return value.split(/[\r\n,;]/).map((item) => item.trim().toLowerCase()).filter(Boolean);
  }
  return [];
}

function renderAll() {
  renderGeneralSection();
  renderRolesSection();
  renderContainers();
}

function renderGeneralSection() {
  if (dom.mainTitle) {
    dom.mainTitle.value = state.config.mainTitle || "";
    dom.mainTitle.disabled = !state.canEdit;
  }
}

function renderRolesSection() {
  if (dom.rolesAdmins) {
    dom.rolesAdmins.value = (state.config.roles.admins || []).join("\n");
    dom.rolesAdmins.disabled = !state.canEdit;
  }
  if (dom.rolesOperators) {
    dom.rolesOperators.value = (state.config.roles.operators || []).join("\n");
    dom.rolesOperators.disabled = !state.canEdit;
  }
  if (dom.rolesViewers) {
    dom.rolesViewers.value = (state.config.roles.viewers || []).join("\n");
    dom.rolesViewers.disabled = !state.canEdit;
  }
}

function renderContainers() {
  if (!dom.containersList || !dom.containerTemplate) return;
  dom.containersList.querySelectorAll("[data-container-index]").forEach((node) => node.remove());
  const containers = state.config.containers || [];
  const hasContainers = containers.length > 0;
  if (dom.containersEmpty) {
    dom.containersEmpty.hidden = hasContainers;
  }
  containers.forEach((container, index) => {
    const card = dom.containerTemplate.content.firstElementChild.cloneNode(true);
    card.dataset.containerIndex = String(index);
    const titleInput = card.querySelector('[data-field="title"]');
    const heading = card.querySelector(".container-title");
    if (titleInput) {
      titleInput.value = container.title || "";
      titleInput.disabled = !state.canEdit;
      titleInput.addEventListener("input", (event) => {
        const value = event.target.value || "";
        state.config.containers[index].title = value;
        heading.textContent = formatContainerTitle(value, index);
        setDirty(true);
      });
    }
    heading.textContent = formatContainerTitle(container.title, index);
    card.classList.toggle("collapsed", !state.expandAll);
    updateContainerSummary(card, container);
    renderObjects(card, container, index);
    const editableButtons = card.querySelectorAll(".btn-editable");
    editableButtons.forEach((btn) => {
      if (!state.canEdit) {
        btn.setAttribute("disabled", "");
      } else {
        btn.removeAttribute("disabled");
      }
    });
    dom.containersList.appendChild(card);
  });
}

function formatContainerTitle(title, index) {
  const base = title && title.trim() ? title.trim() : "Contenedor " + (index + 1);
  return base;
}
function renderObjects(card, container, containerIndex) {
  const wrapper = card.querySelector(".objects-wrap");
  if (!wrapper || !dom.objectTemplate) return;
  wrapper.textContent = "";
  const objects = container.objects || [];
  if (!objects.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Sin widgets. Usa \"Agregar widget\".";
    wrapper.appendChild(empty);
    return;
  }
  objects.forEach((object, objectIndex) => {
    const objCard = dom.objectTemplate.content.firstElementChild.cloneNode(true);
    objCard.dataset.objectIndex = String(objectIndex);
    const header = objCard.querySelector(".object-header h4");
    const toolbar = objCard.querySelector(".object-toolbar");
    const fieldsHost = objCard.querySelector(".object-fields");
    const advancedHost = objCard.querySelector(".object-advanced-fields");
    const advancedWrapper = objCard.querySelector('[data-advanced="wrapper"]');
    const meta = resolveObjectMeta(object.type);
    const labelPreview = object.label && object.label.trim() ? object.label.trim() : "Widget " + (objectIndex + 1);
    header.textContent = `${labelPreview} - ${meta.label}`;
    if (!state.canEdit) {
      toolbar?.querySelectorAll("button").forEach((btn) => btn.setAttribute("disabled", ""));
    }
    buildPrimaryFields(fieldsHost, meta, object, containerIndex, objectIndex);
    const advancedFields = meta.fields.filter((item) => item.section === "advanced");
    if (advancedFields.length && advancedWrapper) {
      advancedWrapper.style.display = "block";
      buildAdvancedFields(advancedHost, advancedFields, object, containerIndex, objectIndex);
    } else if (advancedWrapper) {
      advancedWrapper.style.display = "none";
    }
    wrapper.appendChild(objCard);
  });
}

function buildPrimaryFields(host, meta, object, containerIndex, objectIndex) {
  if (!host) return;
  host.textContent = "";
  const typeGroup = document.createElement("div");
  typeGroup.className = "form-group";
  const typeLabel = document.createElement("label");
  typeLabel.textContent = "Tipo de widget";
  typeGroup.appendChild(typeLabel);
  const typeSelect = document.createElement("select");
  typeSelect.className = "select-input";
  OBJECT_TYPES.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    option.dataset.hint = item.hint;
    typeSelect.appendChild(option);
  });
  const currentType = normalizeType(object.type);
  if (!OBJECT_TYPE_MAP.has(currentType)) {
    const customOption = document.createElement("option");
    customOption.value = object.type || "";
    customOption.textContent = object.type ? `Personalizado (${object.type})` : "Tipo no definido";
    typeSelect.appendChild(customOption);
  }
  typeSelect.value = object.type || meta.value;
  typeSelect.disabled = !state.canEdit;
  typeSelect.addEventListener("change", (event) => {
    updateObjectType(containerIndex, objectIndex, event.target.value);
  });
  typeGroup.appendChild(typeSelect);
  if (meta.hint) {
    const hint = document.createElement("p");
    hint.className = "helper-text";
    hint.textContent = meta.hint;
    typeGroup.appendChild(hint);
  }
  host.appendChild(typeGroup);
  meta.fields.filter((item) => item.section !== "advanced").forEach((field) => {
    host.appendChild(createFieldElement(field, object[field.key], (value) => {
      updateObjectField(containerIndex, objectIndex, field, value);
    }));
  });
}

function buildAdvancedFields(host, fields, object, containerIndex, objectIndex) {
  if (!host) return;
  host.textContent = "";
  fields.forEach((field) => {
    host.appendChild(createFieldElement(field, object[field.key], (value) => {
      updateObjectField(containerIndex, objectIndex, field, value);
    }));
  });
}

function createFieldElement(field, currentValue, onChange) {
  const group = document.createElement("div");
  group.className = "form-group";
  const label = document.createElement("label");
  label.textContent = field.label || field.key;
  group.appendChild(label);
  let input;
  if (field.type === "color") {
    const wrapper = document.createElement("div");
    wrapper.className = "object-color-input";
    const colorInput = document.createElement("input");
    colorInput.type = "color";
    colorInput.value = ensureColor(currentValue);
    colorInput.disabled = !state.canEdit;
    const textInput = document.createElement("input");
    textInput.type = "text";
    textInput.className = "text-input";
    textInput.placeholder = field.placeholder || "#00b4d8";
    textInput.value = ensureColor(currentValue);
    textInput.disabled = !state.canEdit;
    colorInput.addEventListener("input", (event) => {
      const value = event.target.value;
      onChange(value);
      textInput.value = value;
      setDirty(true);
    });
    textInput.addEventListener("change", (event) => {
      const value = ensureColor(event.target.value);
      event.target.value = value;
      colorInput.value = value;
      onChange(value);
      setDirty(true);
    });
    wrapper.append(colorInput, textInput);
    input = wrapper;
  } else {
    const element = document.createElement("input");
    element.className = field.type === "number" ? "number-input" : "text-input";
    element.type = field.type === "number" ? "number" : "text";
    if (field.placeholder) {
      element.placeholder = field.placeholder;
    }
    if (field.type === "number" && typeof currentValue === "number") {
      element.value = String(currentValue);
    } else {
      element.value = currentValue !== undefined && currentValue !== null ? String(currentValue) : "";
    }
    element.disabled = !state.canEdit;
    element.addEventListener("change", (event) => {
      const value = field.type === "number" ? parseNumber(event.target.value) : event.target.value;
      onChange(value);
      setDirty(true);
    });
    input = element;
  }
  group.appendChild(input);
  return group;
}

function updateObjectField(containerIndex, objectIndex, field, value) {
  const container = state.config.containers[containerIndex];
  if (!container) return;
  const object = container.objects[objectIndex];
  if (!object) return;
  if (field.type === "number") {
    if (value === null || value === "" || Number.isNaN(value)) {
      delete object[field.key];
    } else {
      object[field.key] = value;
    }
  } else {
    object[field.key] = value === undefined ? "" : value;
  }
  const cardElement = dom.containersList?.querySelector(`[data-container-index="${containerIndex}"] [data-object-index="${objectIndex}"]`);
  if (cardElement) {
    const header = cardElement.querySelector(".object-header h4");
    if (header) {
      const meta = resolveObjectMeta(object.type);
      const labelPreview = object.label && object.label.trim() ? object.label.trim() : "Widget " + (objectIndex + 1);
      header.textContent = `${labelPreview} - ${meta.label}`;
    }
  }
  updateContainerSummary(dom.containersList.querySelector(`[data-container-index="${containerIndex}"]`), container);
}
function updateObjectType(containerIndex, objectIndex, nextType) {
  const container = state.config.containers[containerIndex];
  if (!container) return;
  const current = container.objects[objectIndex];
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
    value: type || "",
    label: type ? `Tipo ${type}` : "Tipo no definido",
    hint: "Este tipo no esta mapeado, los cambios se guardaran tal cual.",
    defaults: { type: type || "" },
    fields: [
      { key: "label", label: "Nombre visible", type: "text", placeholder: "Widget", section: "primary" },
      { key: "topic", label: "Topic MQTT", type: "text", placeholder: "planta/tag", section: "primary" },
    ],
  };
}

function ensureColor(value) {
  const defaultColor = "#00b4d8";
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
  if (!value) return [];
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}
function addContainer() {
  const container = {
    title: "",
    objects: [],
  };
  state.config.containers.push(container);
  renderContainers();
}

function handleContainerActions(event) {
  const actionBtn = event.target.closest("[data-action]");
  if (!actionBtn) return;
  if (!state.canEdit) return;
  const card = actionBtn.closest("[data-container-index]");
  if (!card) return;
  const containerIndex = Number(card.dataset.containerIndex || "0");
  const action = actionBtn.dataset.action;
  if (action === "add-object") {
    addObject(containerIndex);
  } else if (action === "remove-container") {
    removeContainer(containerIndex);
  } else if (action === "duplicate-container") {
    duplicateContainer(containerIndex);
  } else if (action === "remove-object") {
    const objectCard = actionBtn.closest("[data-object-index]");
    if (objectCard) {
      removeObject(containerIndex, Number(objectCard.dataset.objectIndex || "0"));
    }
  } else if (action === "duplicate-object") {
    const objectCard = actionBtn.closest("[data-object-index]");
    if (objectCard) {
      duplicateObject(containerIndex, Number(objectCard.dataset.objectIndex || "0"));
    }
  }
}

function addObject(containerIndex, type = "level") {
  const container = state.config.containers[containerIndex];
  if (!container) return;
  const meta = resolveObjectMeta(type);
  const object = clone(meta.defaults || { type });
  container.objects.push(object);
  setDirty(true);
  renderContainers();
}

function removeContainer(containerIndex) {
  const container = state.config.containers[containerIndex];
  if (!container) return;
  const confirmed = window.confirm("Eliminar contenedor y todos sus widgets?");
  if (!confirmed) return;
  state.config.containers.splice(containerIndex, 1);
  setDirty(true);
  renderContainers();
}

function duplicateContainer(containerIndex) {
  const container = state.config.containers[containerIndex];
  if (!container) return;
  const copy = clone(container);
  state.config.containers.splice(containerIndex + 1, 0, copy);
  setDirty(true);
  renderContainers();
}

function removeObject(containerIndex, objectIndex) {
  const container = state.config.containers[containerIndex];
  if (!container) return;
  const confirmed = window.confirm("Eliminar este widget?");
  if (!confirmed) return;
  container.objects.splice(objectIndex, 1);
  setDirty(true);
  renderContainers();
}

function duplicateObject(containerIndex, objectIndex) {
  const container = state.config.containers[containerIndex];
  if (!container) return;
  const object = container.objects[objectIndex];
  if (!object) return;
  container.objects.splice(objectIndex + 1, 0, clone(object));
  setDirty(true);
  renderContainers();
}

function toggleAllContainers() {
  state.expandAll = !state.expandAll;
  const cards = dom.containersList?.querySelectorAll("[data-container-index]") || [];
  cards.forEach((card) => {
    card.classList.toggle("collapsed", !state.expandAll);
  });
  if (dom.expandCollapse) {
    dom.expandCollapse.dataset.expanded = String(state.expandAll);
    dom.expandCollapse.textContent = state.expandAll ? "Contraer todo" : "Expandir todo";
  }
}

function updateContainerSummary(card, container) {
  if (!card) return;
  const summaryWidgets = card.querySelector('[data-summary="widgets"]');
  const summaryTopics = card.querySelector('[data-summary="topics"]');
  const widgets = container.objects ? container.objects.length : 0;
  const topics = new Set((container.objects || []).map((obj) => (obj.topic || "").trim()).filter(Boolean));
  if (summaryWidgets) {
    summaryWidgets.textContent = widgets === 1 ? "1 widget" : `${widgets} widgets`;
  }
  if (summaryTopics) {
    summaryTopics.textContent = topics.size === 1 ? "1 topic" : `${topics.size} topics`;
  }
}

function setDirty(isDirty) {
  state.dirty = isDirty;
  if (!isDirty) return;
  setStatus("Tienes cambios sin guardar.", "warning");
}

function applyPermissions() {
  if (dom.root) {
    dom.root.classList.toggle("readonly", !state.canEdit);
  }
  if (document.body) {
    document.body.classList.toggle("readonly", !state.canEdit);
  }
  if (!state.canEdit) {
    dom.saveBtn?.setAttribute("disabled", "");
    dom.importBtn?.setAttribute("disabled", "");
    dom.addContainer?.setAttribute("disabled", "");
  } else {
    dom.saveBtn?.removeAttribute("disabled");
    dom.importBtn?.removeAttribute("disabled");
    dom.addContainer?.removeAttribute("disabled");
  }
}
function updateRoleBadge() {
  dom.roleBadge.textContent = "Rol: " + state.role;
  dom.roleBadge.classList.toggle("chip-connected", state.canEdit);
  dom.roleBadge.classList.toggle("chip-disconnected", !state.canEdit);
}

function setStatus(message, tone = "info") {
  if (!dom.statusBanner) return;
  dom.statusBanner.textContent = message;
  dom.statusBanner.classList.remove("success", "error", "warning");
  if (tone !== "info") {
    dom.statusBanner.classList.add(tone);
  }
}

function parseNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function clone(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function normalizeType(type) {
  return String(type || "").toLowerCase();
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
async function saveConfig() {
  if (!state.canEdit) {
    setStatus("No tienes permisos para guardar.", "warning");
    return;
  }
  try {
    const prepared = prepareConfigForSave();
    const response = await fetch(BACKEND_HTTP + "/config", {
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
  link.download = "scada_config.json";
  link.click();
  URL.revokeObjectURL(url);
  setStatus("Archivo descargado.", "success");
}








