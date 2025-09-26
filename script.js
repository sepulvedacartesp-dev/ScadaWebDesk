const BACKEND_WS = "wss://scadawebdesk.onrender.com/ws";
let ws = null, uid = null;

async function login(email, password) {
  await firebase.auth().signInWithEmailAndPassword(email, password);
  const user = firebase.auth().currentUser;
  uid = user.uid;
  const idToken = await user.getIdToken(true);
  ws = new WebSocket(`${BACKEND_WS}?token=${encodeURIComponent(idToken)}`);

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.topic) {
      console.log("MQTT", msg.topic, msg.payload);
      // TODO: aquí actualizas tus widgets con msg.payload
    }
  };
}

// Publicar sin exponer credenciales
function publishRelative(relativePath, payload, qos=0, retain=false) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const base = `scada/customers/${uid}/`;
  ws.send(JSON.stringify({ type:"publish", topic: base + relativePath, payload, qos, retain }));
}
