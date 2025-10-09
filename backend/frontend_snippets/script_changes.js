// Reemplaza tu conexion MQTT directa por este modulo:
export async function initAuthAndWS(firebaseConfig, backendWsUrl, onMqttMessage) {
  // Cargar Firebase (si no usas modulos, mueve esto a una etiqueta <script> con compat)
  firebase.initializeApp(firebaseConfig);

  let ws = null;
  let uid = null;
  let empresaId = null;

  async function login(email, password) {
    await firebase.auth().signInWithEmailAndPassword(email, password);
    const user = firebase.auth().currentUser;
    uid = user.uid;
    const idToken = await user.getIdToken(true);
    const wsUrl = backendWsUrl + "?token=" + encodeURIComponent(idToken);
    ws = new WebSocket(wsUrl);

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "hello") {
        uid = msg.uid;
        empresaId = msg.empresaId || null;
        return;
      }
      if (msg.topic) onMqttMessage(msg.topic, msg.payload);
    };

    return uid;
  }

  function publish(relativePath, payload, qos=0, retain=false) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!empresaId) {
      console.warn("Empresa no asignada aun; espera el mensaje hello del backend.");
      return;
    }
    const base = "scada/customers/" + empresaId + "/";
    ws.send(JSON.stringify({type: "publish", topic: base + relativePath, payload, qos, retain}));
  }

  return { login, publish };
}
