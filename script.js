const BACKEND_HTTP = "https://scadawebdesk.onrender.com";
const BACKEND_WS = "wss://scadawebdesk.onrender.com/ws";

let ws = null;
let uid = null;
let reconnectTimer = null;
let lastToken = null;

const loginForm = document.getElementById("login-form");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const statusLabel = document.getElementById("status");
const logArea = document.getElementById("log");
const logoutBtn = document.getElementById("logout-btn");

function setStatus(text) {
  if (statusLabel) {
    statusLabel.textContent = text;
  }
}

function appendLog(entry) {
  if (!logArea) return;
  const now = new Date().toISOString();
  logArea.textContent += `[${now}] ${entry}\n`;
  logArea.scrollTop = logArea.scrollHeight;
}

async function login(email, password) {
  setStatus("Iniciando sesion...");
  await firebase.auth().signInWithEmailAndPassword(email, password);
  setStatus("Sesion iniciada, conectando...");
}

function disconnectWs(reason) {
  if (ws) {
    ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
    try { ws.close(); } catch (_) { /* ignore */ }
  }
  ws = null;
  if (reason) {
    appendLog(`WS cerrado (${reason})`);
  }
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
      setStatus(`Conectado como ${user.email}`);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "hello") {
          uid = msg.uid;
          appendLog(`HELLO uid=${uid}`);
        } else if (msg.type === "ack") {
          appendLog(`ACK ${msg.topic}`);
        } else if (msg.type === "error") {
          appendLog(`ERROR ${msg.error}`);
        } else if (msg.topic) {
          appendLog(`MQTT ${msg.topic} ${JSON.stringify(msg.payload)}`);
        }
      } catch (err) {
        appendLog(`Mensaje WS invalido: ${err}`);
      }
    };

    ws.onclose = (event) => {
      appendLog(`WS cerrado codigo=${event.code}`);
      ws = null;
      if (firebase.auth().currentUser) {
        scheduleReconnect();
      } else {
        setStatus("Sesion cerrada");
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

function normalizeRelativePath(relPath) {
  return relPath.split("/").filter(Boolean).join("/");
}

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
      emailInput.value = "";
      passwordInput.value = "";
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
    uid = null;
    disconnectWs("logout");
    await firebase.auth().signOut();
    setStatus("Sesion cerrada");
  });
}

firebase.auth().onAuthStateChanged(async (user) => {
  clearTimeout(reconnectTimer);
  if (user) {
    setStatus(`Sesion activa: ${user.email}`);
    uid = user.uid;
    await connectWs(user);
  } else {
    uid = null;
    lastToken = null;
    disconnectWs();
    setStatus("Sin sesion");
  }
});

firebase.auth().onIdTokenChanged(async (user) => {
  if (user) {
    await connectWs(user);
  }
});

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

