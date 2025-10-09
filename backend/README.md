# MQTT Web Bridge (FastAPI + Firebase Auth + HiveMQ)

Este backend actua como puente seguro entre el frontend estatico, Firebase Authentication y el broker MQTT. Las funciones principales son:
- Validar tokens ID emitidos por Firebase antes de abrir la sesion WebSocket o aceptar publicaciones HTTP.
- Conectarse a HiveMQ Cloud usando credenciales privadas almacenadas en variables de entorno (Render secrets).
- Reenviar todos los mensajes MQTT permitidos hacia los navegadores conectados via WebSocket.
- Restringir la lectura y la escritura al scope `TOPIC_BASE/{empresaId}/{uid}/...` mas los prefijos publicos configurados.

## Requisitos previos
- Proyecto de Firebase con Authentication (Email/Password) habilitado y al menos un usuario de prueba.
- Instancia de HiveMQ Cloud (puerto TLS 8883) o un broker MQTT compatible.
- Cuenta en Render.com (free tier) para desplegar este backend como Web Service.
- Frontend estatico (GitHub Pages + Hostinger) que cargue Firebase Web SDK.

## Variables de entorno
Crea un archivo `.env` a partir de `.env.example` y completa los valores reales. Nunca subas secretos al repositorio.
```env
FRONTEND_ORIGIN=https://TU-DOMINIO-EN-HOSTINGER
FIREBASE_PROJECT_ID=scadaweb-64eba
# FIREBASE_SERVICE_ACCOUNT=<JSON OPCIONAL PARA REVOCATION CHECK>

HIVEMQ_HOST=xxxxxx.s1.eu.hivemq.cloud
HIVEMQ_PORT=8883
HIVEMQ_USERNAME=USUARIO_MQTT
HIVEMQ_PASSWORD=PASSWORD_MQTT

MQTT_TLS=1
MQTT_TLS_INSECURE=0
MQTT_CA_CERT_PATH=

TOPIC_BASE=scada/customers
PUBLIC_ALLOWED_PREFIXES=public/broadcast
DEFAULT_EMPRESA_ID=default
MASTER_ADMIN_EMAILS=maestro@tuempresa.com
MASTER_ADMIN_ROLE_NAMES=master,root
```
Si necesitas validar revocacion de tokens, agrega `FIREBASE_SERVICE_ACCOUNT` con el JSON completo del service account.

## Ejecucion local
```bash
python -m venv .venv
# Windows Powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
- Healthcheck: `GET http://127.0.0.1:8000/health`
- WebSocket: `ws://127.0.0.1:8000/ws?token=<ID_TOKEN>`
- Publicar: `POST http://127.0.0.1:8000/publish` con header `Authorization: Bearer <ID_TOKEN>` y cuerpo JSON `{ "topic": "scada/customers/<empresaId>/demo", "payload": {"ok": true} }`.

## Despliegue en Render
Configura el servicio exactamente con los siguientes valores:
- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Runtime Environment Variables:
  - `PYTHON_VERSION=3.11.9`
  - `FRONTEND_ORIGIN` (tu dominio Hostinger o `http://127.0.0.1:8001` para pruebas locales)
  - `FIREBASE_PROJECT_ID=scadaweb-64eba`
  - `FIREBASE_SERVICE_ACCOUNT` (solo si aplicas revocation check)
  - `HIVEMQ_HOST`, `HIVEMQ_PORT`, `HIVEMQ_USERNAME`, `HIVEMQ_PASSWORD`
  - `MQTT_TLS=1`, `MQTT_TLS_INSECURE=0`, `MQTT_CA_CERT_PATH=`
  - `TOPIC_BASE=scada/customers`
  - `PUBLIC_ALLOWED_PREFIXES=public/broadcast`
  - `DEFAULT_EMPRESA_ID=default`
  - `MASTER_ADMIN_EMAILS=maestro@tuempresa.com`
  - `MASTER_ADMIN_ROLE_NAMES=master,root`

## Integracion del Frontend
1. Incluye los SDK compat de Firebase en `index.html`.
2. Inicializa Firebase con la configuracion del proyecto `scadaweb-64eba`.
3. Implementa login Email/Password y recupera el `ID Token` actual con `firebase.auth().currentUser.getIdToken(true)`.
4. Abre el WebSocket contra `wss://scadawebdesk.onrender.com/ws?token=<ID_TOKEN>`.
5. Publica usando el mensaje JSON `{type:"publish", topic, payload, qos, retain}`.
6. Para publicar en tu scope, usa ``const base = `scada/customers/${empresaId}/`;`` y concatena los paths relativos definidos para tu empresa en `scada_configs/<empresaId>_Scada_Config.json`.

## Gestion de clientes multiempresa
- `GET /tenants`: lista todas las empresas configuradas (solo para administradores maestros).
- `GET /tenants/{empresaId}`: devuelve el detalle de una empresa.
- `POST /tenants`: crea una nueva empresa (`empresaId`, `name`, `description`, `cloneFrom`). Genera automaticamente el archivo `scada_configs/<empresaId>_Scada_Config.json`.
- `PUT /tenants/{empresaId}`: actualiza nombre, descripcion o estado `active`.
- `GET /config?empresaId=<id>` y `PUT /config?empresaId=<id>` permiten a los maestros editar la configuracion de cualquier cliente.

## Pruebas y criterios de aceptacion
1. `GET https://scadawebdesk.onrender.com/health` responde `{ "status": "ok" }`.
2. Login correcto en el frontend muestra el mensaje `hello` inicial con `uid` y `allowed_prefixes` desde el WebSocket.
3. Llamada `publishRelative("lab/echo", { msg: "hola", ts: Date.now() })` emite el `ack` y el mensaje se refleja en la consola del navegador.
4. Publicar desde HiveMQ (con las credenciales del backend) en `scada/customers/<empresaId>/lab/externo` se refleja en el navegador.
5. (Opcional) Solicitud `GET /` o `/publish` con token invalido responde `401`.
6. Render mantiene el servicio activo tras cold start (espera hasta 50 s en primer request).

## Buenas practicas adicionales
- Mantener `MQTT_TLS_INSECURE=0`; solo cambiar a 1 si usas certificados autofirmados.
- Configurar ACLs en HiveMQ para reforzar el scope MQTT.
- Agregar rate limiting o validaciones especificas si vas a exponer controles criticos.
- Rotar contrasenas MQTT periodicamente y actualizarlas en Render.

