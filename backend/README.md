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
MQTT_KEEPALIVE=30
MQTT_BROKER_PROFILES={"default":{"host":"xxxxxx.s1.eu.hivemq.cloud","port":8883,"username":"USUARIO_MQTT","password":"PASSWORD_MQTT"}}

TOPIC_BASE=scada/customers
PUBLIC_ALLOWED_PREFIXES=public/broadcast
DEFAULT_EMPRESA_ID=default
MASTER_ADMIN_EMAILS=maestro@tuempresa.com
MASTER_ADMIN_ROLE_NAMES=master,root
DATABASE_URL=postgresql://user:password@host:5432/trends
TRENDS_FETCH_LIMIT=5000
DEFAULT_TRENDS_RANGE_HOURS=24
DIAS_RETENCION_HISTORICO=30
QUOTE_DB_MIN_POOL_SIZE=1
QUOTE_DB_MAX_POOL_SIZE=5
QUOTE_DB_TIMEOUT=10
```
Puedes indicar múltiples orígenes separándolos por comas en `FRONTEND_ORIGIN`. Si usas `*`, el backend desactiva `allow_credentials` para cumplir con CORS.
`MQTT_BROKER_PROFILES` permite definir un mapa JSON plano `{ "claveBroker": { ... } }`. Cada entrada hereda las credenciales base (`HIVEMQ_*`) y puede sobrescribir `host`, `port`, `username`, `password`, `tls`, `tlsInsecure`, `caCertPath`, `clientId` y `keepalive`. Usa la clave `default` para la configuración por omisión y agrega entradas adicionales (`cliente1`, `cliente2`, etc.) para asignarlas a empresas concretas.
Si necesitas validar revocacion de tokens, agrega `FIREBASE_SERVICE_ACCOUNT` con el JSON completo del service account.

- `FIREBASE_WEB_API_KEY` (opcional): Web API Key del proyecto Firebase. Permite que el backend dispare correos de invitacion/reset usando `accounts:sendOobCode`.
- `FIREBASE_EMAIL_CONTINUE_URL` (opcional): URL de redireccion usada en los enlaces de restablecimiento generados (`ActionCodeSettings`).
- `FIREBASE_AUTH_TIMEOUT` (opcional, por defecto `10` segundos): timeout HTTP para las llamadas al servicio Identity Toolkit.
- Motor de alarmas 24/7 (Zoho Mail):
  - `ENABLE_ALARM_MONITOR=1`
  - `ALARM_SMTP_HOST=smtp.zoho.com`
  - `ALARM_SMTP_PORT=587`
  - `ALARM_SMTP_USERNAME=notificaciones@surnex.cl`
  - `ALARM_SMTP_PASSWORD=<clave_app_zoho>`
  - `ALARM_SMTP_STARTTLS=1`
  - `ALARM_SMTP_USE_SSL=0`
  - `ALARM_SMTP_TIMEOUT=15`
  - `ALARM_EMAIL_FROM=notificaciones@surnex.cl`
  - `ALARM_EMAIL_FROM_NAME=SurNex Alarmas`
  - `ALARM_EMAIL_SUBJECT_PREFIX=[Alarma SCADA]`
  - `ALARM_EMAIL_REPLY_TO=`
  - `ALARM_RULES_REFRESH_SECONDS=60`
  - `ALARM_QUEUE_MAXSIZE=2048`

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

## Migraciones y seeds del Cotizador
- Aplica el esquema actualizado con Alembic:
  ```bash
  alembic upgrade head
  ```
  Asegurate de que `DATABASE_URL` este configurada en tu entorno antes de ejecutar el comando.
- Para inicializar el catalogo base y un cliente de demostracion:
  ```bash
  python -m backend.scripts.seed_quotes
  ```
- Si quieres aplicar migraciones solo cuando existan cambios pendientes:
  ```bash
  python -m backend.scripts.migrate_if_needed
  ```
- Cuando necesites modificar el esquema, crea una nueva revision:
  ```bash
  alembic revision -m "descripcion del cambio"
  # editar el archivo generado en migrations/versions/
  alembic upgrade head
  ```

En Render agrega `alembic upgrade head` al paso de build o despliegue para mantener la base sincronizada antes de iniciar `uvicorn`.

## Despliegue en Render
Configura el servicio exactamente con los siguientes valores:
- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Runtime Environment Variables:
  - `PYTHON_VERSION=3.11.9`
- `FRONTEND_ORIGIN` (tu dominio Hostinger o `http://127.0.0.1:8001` para pruebas locales; acepta lista separada por comas)
  - `FIREBASE_PROJECT_ID=scadaweb-64eba`
  - `FIREBASE_SERVICE_ACCOUNT` (solo si aplicas revocation check)
  - `HIVEMQ_HOST`, `HIVEMQ_PORT`, `HIVEMQ_USERNAME`, `HIVEMQ_PASSWORD`
  - `MQTT_TLS=1`, `MQTT_TLS_INSECURE=0`, `MQTT_CA_CERT_PATH=`
  - `TOPIC_BASE=scada/customers`
  - `PUBLIC_ALLOWED_PREFIXES=public/broadcast`
  - `DEFAULT_EMPRESA_ID=default`
  - `MASTER_ADMIN_EMAILS=maestro@tuempresa.com`
  - `MASTER_ADMIN_ROLE_NAMES=master,root`
  - `DATABASE_URL=postgresql://user:password@hostname:5432/trends`
  - `TRENDS_FETCH_LIMIT=5000`
  - `DEFAULT_TRENDS_RANGE_HOURS=24`
  - `DIAS_RETENCION_HISTORICO=30`

### Servicio de tendencias historicas
- `GET /api/tendencias/tags`: lista los tags disponibles para la empresa autenticada (acepta `empresaId` cuando el usuario es maestro).
- `GET /api/tendencias`: entrega la serie de tiempo y estadisticas claves (`latest`, `min`, `max`, `avg`) filtrando por `tag`, rango (`from`, `to`) y resolucion (`raw`, `5m`, `15m`, `1h`, `1d`).
- `GET /trend`: sirve la pagina `trend.html` con la interfaz de visualizacion.

Configura en Render una base PostgreSQL accesible via `DATABASE_URL` y un cron job/worker que ejecute la sentencia de retencion respetando `DIAS_RETENCION_HISTORICO`.

### Motor de alarmas 24/7
- El worker `backend/workers/trends_ingest/worker.py` ejecuta en paralelo la ingesta de tendencias y la evaluación de reglas almacenadas en `alarm_rules`. Cada valor que llega via MQTT se compara contra los umbrales activos y, si corresponde, se registra un evento en `alarm_events` y se dispara un correo usando Zoho Mail.
- Requisitos:
  - Variables de entorno de la sección anterior (`ENABLE_ALARM_MONITOR`, `ALARM_SMTP_*`, `ALARM_EMAIL_*`, `ALARM_RULES_REFRESH_SECONDS`, `ALARM_QUEUE_MAXSIZE`).
  - Credenciales SMTP de `notificaciones@surnex.cl` (clave de aplicación y TLS STARTTLS).
  - Base PostgreSQL accesible desde el worker (`DATABASE_URL`).
- Ejecución local:
  ```bash
  cd backend/workers/trends_ingest
  pip install -r requirements.txt
  # exporta las variables necesarias y luego
  python worker.py
  ```
  El stdout mostrará la cantidad de reglas activas y registrará los correos enviados o errores de SMTP.
- Despliegue: en Render (u otro proveedor) publica un proceso worker adicional o ejecuta el script en el mismo servicio usando `Procfile` (`web` + `worker`). Asegúrate de correr `alembic upgrade head` antes de iniciar para crear `alarm_rules` y `alarm_events`.

### API de alarmas
- `GET /api/alarms/rules`: lista las reglas de la empresa autenticada (`empresaId` opcional para administradores maestros).
- `POST /api/alarms/rules`: crea una regla (`tag`, `operator` ∈ {`gte`,`lte`,`eq`}, `threshold`, `valueType`, `notifyEmail`, `cooldownSeconds`, `active`).
- `PUT /api/alarms/rules/{id}`: actualiza una regla existente.
- `DELETE /api/alarms/rules/{id}`: elimina la regla y sus eventos asociados.
- `GET /api/alarms/events`: entrega el historial reciente (`limit`, `tag` opcionales).

Las rutas requieren un token válido de Firebase y rol `admin` de la empresa (o `master/config`). El frontend `config.html` expone un formulario para gestionar estas reglas sin tocar `config.html`.

## Integracion del Frontend
1. Incluye los SDK compat de Firebase en `dashboard.html`.
2. Inicializa Firebase con la configuracion del proyecto `scadaweb-64eba`.
3. Implementa login Email/Password y recupera el `ID Token` actual con `firebase.auth().currentUser.getIdToken(true)`.
4. Abre el WebSocket contra `wss://scadawebdesk.onrender.com/ws?token=<ID_TOKEN>`.
5. Publica usando el mensaje JSON `{type:"publish", topic, payload, qos, retain}`.
6. Para publicar en tu scope, usa ``const base = `scada/customers/${empresaId}/`;`` y concatena los paths relativos definidos para tu empresa en `scada_configs/<empresaId>_Scada_Config.json`.

## Gestion de clientes multiempresa
- `GET /tenants`: lista todas las empresas configuradas (solo para administradores maestros).
- `GET /tenants/{empresaId}`: devuelve el detalle de una empresa.
- `POST /tenants`: crea una nueva empresa (`empresaId`, `name`, `description`, `cloneFrom`, `mqttBrokerKey`). Genera automaticamente el archivo `scada_configs/<empresaId>_Scada_Config.json`.
- `PUT /tenants/{empresaId}`: actualiza nombre, descripcion, estado `active` y la asignación `mqttBrokerKey`.
- `GET /config?empresaId=<id>` y `PUT /config?empresaId=<id>` permiten a los maestros editar la configuracion de cualquier cliente.

- `GET /users?empresaId=<id>`: lista los usuarios asignados a la empresa.
- `POST /users`: crea un usuario en Firebase, asigna claims (`empresaId`, `scadaRole`) y actualiza la configuracion local (`roles`).
- `DELETE /users/{uid}`: elimina al usuario de Firebase y lo remueve de la configuracion.
- `POST /users/{uid}/reset-link`: genera un enlace seguro de restablecimiento y, si hay API key, envia el correo de invitacion/reset.

## Pruebas y criterios de aceptacion
1. `GET https://scadawebdesk.onrender.com/health` responde `{ "status": "ok" }`.
2. Login correcto en el frontend muestra el mensaje `hello` inicial con `uid`, `empresaId`, `allowed_prefixes` y `broker` desde el WebSocket.
3. Llamada `publishRelative("lab/echo", { msg: "hola", ts: Date.now() })` emite el `ack` y el mensaje se refleja en la consola del navegador.
4. El `ack` de `/publish` y del WebSocket incluye la clave de broker utilizada (`broker`).
5. Publicar desde HiveMQ (con las credenciales del broker asignado) en `scada/customers/<empresaId>/lab/externo` se refleja en el navegador.
6. (Opcional) Solicitud `GET /` o `/publish` con token invalido responde `401`.
7. Render mantiene el servicio activo tras cold start (espera hasta 50 s en primer request).
8. `GET /api/alarms/rules?empresaId=<id>` devuelve la lista de reglas (requiere rol `admin`).
9. `POST /api/alarms/rules` con `{"tag":"scada/customers/demo/trend/temp","operator":"gte","threshold":80,"valueType":"number","notifyEmail":"alertas@demo.cl","cooldownSeconds":300}` responde con la regla persistida y vuelve a aparecer en el listado.
10. Publicar un valor que cumpla el umbral genera un registro en `alarm_events` y envía un correo desde `notificaciones@surnex.cl`. Reintentos dentro del `cooldownSeconds` no duplican notificaciones.

## Buenas practicas adicionales
- Mantener `MQTT_TLS_INSECURE=0`; solo cambiar a 1 si usas certificados autofirmados.
- Configurar ACLs en HiveMQ para reforzar el scope MQTT.
- Agregar rate limiting o validaciones especificas si vas a exponer controles criticos.
- Rotar contrasenas MQTT periodicamente y actualizarlas en Render.

