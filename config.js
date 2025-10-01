const BACKEND_HTTP = "https://scadawebdesk.onrender.com";

const state = {
  token: null,
  role: "viewer",
  canEdit: false,
};

const dom = {
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
  editor: document.getElementById("config-editor"),
  reloadBtn: document.getElementById("reload-btn"),
  saveBtn: document.getElementById("save-btn"),
  downloadBtn: document.getElementById("download-btn"),
  importBtn: document.getElementById("import-btn"),
  formatBtn: document.getElementById("format-btn"),
  importInput: document.getElementById("importInput"),
};

document.addEventListener("DOMContentLoaded", () => {
  attachHandlers();
  firebase.auth().onAuthStateChanged(onAuthStateChanged);
});

function attachHandlers() {
  dom.reloadBtn?.addEventListener("click", () => loadConfig(true));
  dom.saveBtn?.addEventListener("click", saveConfig);
  dom.downloadBtn?.addEventListener("click", downloadConfig);
  dom.formatBtn?.addEventListener("click", formatJson);
  dom.importBtn?.addEventListener("click", () => dom.importInput?.click());
  dom.importInput?.addEventListener("change", handleImportFile);
  dom.openLoginBtn?.addEventListener("click", () => {
    if (!firebase.auth().currentUser) {
      dom.loginDialog.showModal();
    }
  });
  dom.closeLoginBtn?.addEventListener("click", () => {
    dom.loginDialog.close();
    dom.loginForm.reset();
  });
  dom.loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = dom.emailInput.value.trim();
    const password = dom.passwordInput.value;
    if (!email || !password) {
      setStatus("Email y contrasena requeridos", "warning");
      return;
    }
    try {
      await firebase.auth().signInWithEmailAndPassword(email, password);
      dom.loginDialog.close();
      dom.loginForm.reset();
      setStatus("Sesion iniciada.", "success");
    } catch (error) {
      setStatus((error && error.message) || "No se pudo iniciar sesion", "error");
    }
  });
  dom.logoutBtn?.addEventListener("click", async () => {
    await firebase.auth().signOut();
  });
}

async function onAuthStateChanged(user) {
  if (user) {
    dom.sessionStatus.textContent = "Sesion activa: " + user.email;
    dom.logoutBtn.removeAttribute("disabled");
    dom.openLoginBtn.setAttribute("disabled", "");
    await refreshToken(user);
    await loadConfig();
  } else {
    dom.sessionStatus.textContent = "Sin sesion";
    dom.logoutBtn.setAttribute("disabled", "");
    dom.openLoginBtn.removeAttribute("disabled");
    state.token = null;
    state.role = "viewer";
    state.canEdit = false;
    dom.editor.value = "";
    updateRoleBadge();
    applyPermissions();
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
      throw new Error(text ? text : orFallback(response.status));
    }
    const payload = await response.json();
    const config = payload.config || {};
    state.role = payload.role || determineRole(config, user.email);
    state.canEdit = state.role === "admin";
    dom.editor.value = JSON.stringify(config, null, 2);
    updateRoleBadge();
    applyPermissions();
    setStatus(state.canEdit ? "Configuracion cargada. Puedes editar." : "Configuracion cargada en modo lectura.", state.canEdit ? "success" : "info");
  } catch (error) {
    console.error("loadConfig", error);
    setStatus("Error al cargar: " + ((error && error.message) || error), "error");
  }
}

function orFallback(code) {
  return "Error " + code;
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
    return value.split(/[
,;]/).map((item) => item.trim().toLowerCase()).filter(Boolean);
  }
  return [];
}

function updateRoleBadge() {
  dom.roleBadge.textContent = "Rol: " + state.role;
  dom.roleBadge.classList.toggle("chip-connected", state.canEdit);
  dom.roleBadge.classList.toggle("chip-disconnected", !state.canEdit);
}

function applyPermissions() {
  if (state.canEdit) {
    dom.saveBtn.removeAttribute("disabled");
    dom.importBtn.removeAttribute("disabled");
    dom.editor.removeAttribute("readonly");
  } else {
    dom.saveBtn.setAttribute("disabled", "");
    dom.importBtn.setAttribute("disabled", "");
    dom.editor.setAttribute("readonly", "");
  }
}

function setStatus(message, tone = "info") {
  if (!dom.statusBanner) return;
  dom.statusBanner.textContent = message;
  dom.statusBanner.classList.remove("success", "error", "warning");
  if (tone !== "info") {
    dom.statusBanner.classList.add(tone);
  }
}

function formatJson() {
  const text = dom.editor.value.trim();
  if (!text) return;
  try {
    const parsed = JSON.parse(text);
    dom.editor.value = JSON.stringify(parsed, null, 2);
    setStatus("JSON formateado.", "success");
  } catch (error) {
    setStatus("JSON invalido: " + error.message, "error");
  }
}

async function saveConfig() {
  if (!state.canEdit) {
    setStatus("No tienes permisos para guardar.", "warning");
    return;
  }
  try {
    const text = dom.editor.value.trim();
    if (!text) {
      setStatus("El contenido esta vacio.", "warning");
      return;
    }
    const parsed = JSON.parse(text);
    const response = await fetch(BACKEND_HTTP + "/config", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + state.token,
      },
      body: JSON.stringify(parsed),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail && detail.detail ? detail.detail : orFallback(response.status));
    }
    setStatus("Configuracion guardada correctamente.", "success");
  } catch (error) {
    console.error("saveConfig", error);
    setStatus("No se pudo guardar: " + ((error && error.message) || error), "error");
  }
}

function downloadConfig() {
  const text = dom.editor.value;
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "scada_config.json";
  link.click();
  URL.revokeObjectURL(url);
  setStatus("Archivo descargado.", "success");
}

function handleImportFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const text = String((e.target && e.target.result) || "");
      JSON.parse(text);
      dom.editor.value = text;
      setStatus("Archivo importado. Recuerda guardar para aplicar en el servidor.", "info");
    } catch (error) {
      setStatus("Archivo invalido: " + error.message, "error");
    }
  };
  reader.readAsText(file, "utf-8");
  event.target.value = "";
}
