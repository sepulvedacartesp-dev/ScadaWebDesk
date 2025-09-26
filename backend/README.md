# MQTT Web Bridge (FastAPI + Firebase + HiveMQ)

Este backend intermedio permite:
- Validar usuarios vía **Firebase Authentication** (token ID).
- Conectarse a **HiveMQ** (u otro broker MQTT) con **credenciales seguras**.
- Exponer un **WebSocket** para que el frontend reciba datos en tiempo real y publique sin conocer credenciales del broker.
- Restringir temas MQTT por **UID de Firebase**: cada usuario sólo accede a `TOPIC_BASE/{uid}/...`

## 1) Requisitos
- Una cuenta de **Firebase** (plan gratuito) con *Authentication* activado (email/contraseña).
- Un broker **HiveMQ** (puede ser HiveMQ Cloud).
- Una cuenta en **Render.com** o **Railway.app** (plan gratuito) para desplegar este backend.
- Tu frontend web (GitHub Pages + Hostinger) que hará login con Firebase.

## 2) Firebase: configuración rápida
1. Crea un **Proyecto** en Firebase.
2. En **Authentication → Sign-in method**, habilita **Email/Password**.
3. En **Project settings → General → Your apps → Web app**, copia la configuración web (apiKey, authDomain, etc.).
4. Crea al menos un **usuario de prueba** en Authentication → Users.

> Nota: el backend verifica el **ID Token** de Firebase con `firebase_admin`. Sólo necesitas el `FIREBASE_PROJECT_ID` (el mismo que ves en Firebase).

## 3) Variables de entorno
Crea un archivo `.env` a partir de `.env.example` y completa los valores:
```
FRONTEND_ORIGIN=https://tu-dominio.com
FIREBASE_PROJECT_ID=tu-proyecto-firebase-id

HIVEMQ_HOST=xxxxxxxx.s1.eu.hivemq.cloud
HIVEMQ_PORT=8883
HIVEMQ_USERNAME=usuario_mqtt
HIVEMQ_PASSWORD=contraseña_mqtt

MQTT_TLS=1
MQTT_TLS_INSECURE=0
MQTT_CA_CERT_PATH=

TOPIC_BASE=scada/customers
PUBLIC_ALLOWED_PREFIXES=public/broadcast
```

## 4) Ejecutar localmente (opcional)
```bash
python -m venv .venv
source .venv/bin/activate  # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
- WebSocket: `ws://localhost:8000/ws?token=ID_TOKEN`
- Publicar: `POST http://localhost:8000/publish` con header `Authorization: Bearer ID_TOKEN`

## 5) Despliegue en Render (gratis)
1. Sube esta carpeta a un repositorio en GitHub (puede ser un subfolder `backend/` de tu repo existente).
2. En Render, **New + Web Service** → conecta tu repo.
3. **Environment**: `Python 3.11` (o similar).
4. **Build Command**: `pip install -r requirements.txt`
5. **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
6. En **Environment Variables**, agrega todas las del `.env`.
7. Deploy. Render te dará una URL tipo `https://tuapp.onrender.com`.

> Nota: En el plan gratuito puede haber *cold start* (primer request tarda unos segundos). Luego funciona fluido.

## 6) Frontend: Login con Firebase y WebSocket
Incluye Firebase mediante CDN en tu HTML:
```html
<script src="https://www.gstatic.com/firebasejs/10.12.4/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.12.4/firebase-auth-compat.js"></script>
<script>
  const firebaseConfig = {
    apiKey: "TU_API_KEY",
    authDomain: "TU_AUTH_DOMAIN",
    projectId: "TU_PROJECT_ID",
  };
  firebase.initializeApp(firebaseConfig);
</script>
```

Ejemplo mínimo de login y conexión al WebSocket:
```html
<script>
let ws = null;
let idToken = null;

// Login básico (email+password)
async function login(email, password) {
  await firebase.auth().signInWithEmailAndPassword(email, password);
  const user = firebase.auth().currentUser;
  idToken = await user.getIdToken(/* forceRefresh */ true);
  connectWS();
}

function connectWS() {
  const wsUrl = "wss://TU_BACKEND_URL/ws?token=" + encodeURIComponent(idToken);
  ws = new WebSocket(wsUrl);
  ws.onopen = () => console.log("WS abierto");
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "hello") {
      console.log("Conectado como", msg.uid, "prefixes:", msg.allowed_prefixes);
    } else if (msg.topic) {
      // Mensaje desde MQTT → frontend
      // msg = {topic, payload, qos, retain}
      console.log("MQTT", msg.topic, msg.payload);
      // TODO: actualizar tus widgets/indicadores con msg.payload
    } else if (msg.type === "error") {
      console.error("WS error:", msg.error);
    }
  };
  ws.onclose = () => console.log("WS cerrado");
}

// Publicar vía WebSocket (sin exponer credenciales)
function publish(topic, payload, qos=0, retain=false) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({type: "publish", topic, payload, qos, retain}));
}
</script>
```

> Importante: El servidor **restringe** por UID los temas permitidos. Sólo podrás publicar/recibir bajo `TOPIC_BASE/{uid}/...`.

## 7) Migrar tu app actual
- Quita cualquier conexión MQTT directa desde el navegador.
- Mantén tu `scada_config.json` con la lista de *topics* relativos (por ejemplo, `nivel`, `bomba/status`).
- Al iniciar sesión, determina el prefijo del usuario: `const base = "scada/customers/" + UID + "/";`
- Para *subscribe*: tu backend ya reenvía todo lo que coincida con ese prefijo; tú sólo filtra por `topic.startsWith(base)` si lo necesitas.
- Para *publish*: usa `publish(base + "comandos/bomba", {start: true})`.

## 8) Seguridad adicional recomendada
- En HiveMQ, usa **TLS (8883)** y **ACLs** si es posible.
- En el backend, ajusta `PUBLIC_ALLOWED_PREFIXES` sólo si realmente necesitas canales compartidos.
- Considera *rate limiting* y validaciones de payload en `/publish` si aceptas control de equipos.
