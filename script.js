// --- Configuración MQTT ---
const MQTT_HOST = "550bffa3b80b4956be6a94fdcd65b4d1.s1.eu.hivemq.cloud";
const MQTT_PORT = 8884;
const MQTT_PATH = "/mqtt";
const MQTT_USERNAME = "Webclient";
const MQTT_PASSWORD = "Webclient2025";
const CLIENT_ID = "web_scada_" + Math.random().toString(16).substr(2, 8);

// Tópicos
const TOPIC_LEVEL_READ = "PLC/Nivel";
const TOPIC_PUMP_STATE_READ = "PLC/PumpSts";
const TOPIC_PUMP_CMD_START = "PLC/PumpCmdStart";
const TOPIC_PUMP_CMD_STOP  = "PLC/PumpCmdStop";

// --- Elementos HTML ---
const tankLevelDiv = document.getElementById("tank-level");
const levelValueSpan = document.getElementById("level-value");
const pumpStateSpan = document.getElementById("pump-state");
const pumpIndicator = document.getElementById("pump-indicator");
const startPumpBtn = document.getElementById("start-pump-btn");
const stopPumpBtn = document.getElementById("stop-pump-btn");

let client;

// --- Funciones MQTT ---
function connectMQTT() {
  client = new Paho.MQTT.Client(MQTT_HOST, Number(MQTT_PORT), MQTT_PATH, CLIENT_ID);

  client.onConnectionLost = onConnectionLost;
  client.onMessageArrived = onMessageArrived;

  const options = {
    timeout: 3,
    userName: MQTT_USERNAME,
    password: MQTT_PASSWORD,
    useSSL: true,
    onSuccess: onConnectSuccess,
    onFailure: onConnectFailure,
    cleanSession: true
  };

  console.log("Intentando conectar a MQTT...");
  client.connect(options);
}

function onConnectSuccess() {
  console.log("Conectado a MQTT!");
  client.subscribe(TOPIC_LEVEL_READ);
  client.subscribe(TOPIC_PUMP_STATE_READ);
}

function onConnectFailure(resp) {
  console.log("Fallo conexión:", resp.errorMessage);
  setTimeout(connectMQTT, 5000);
}

function onConnectionLost(resp) {
  if (resp.errorCode !== 0) {
    console.log("Conexión perdida:", resp.errorMessage);
    setTimeout(connectMQTT, 5000);
  }
}

function onMessageArrived(message) {
  console.log(`Mensaje recibido: ${message.destinationName} = ${message.payloadString}`);

  if (message.destinationName === TOPIC_LEVEL_READ) {
    let level = parseFloat(message.payloadString);
    if (!isNaN(level)) {
      level = Math.max(0, Math.min(100, level));
      tankLevelDiv.style.height = level + "%";
      levelValueSpan.textContent = level.toFixed(0);
    }
  }

  if (message.destinationName === TOPIC_PUMP_STATE_READ) {
    // Interpretar la carga como booleano
    let state;
    try {
      // si viene como "true"/"false" en texto
      state = JSON.parse(message.payloadString.toLowerCase());
    } catch {
      // fallback: aceptar "1"/"0"
      state = message.payloadString === "1";
    }

    if (state === true) {
      pumpStateSpan.textContent = "ENCENDIDA";
      pumpStateSpan.style.color = "green";
      pumpIndicator.style.backgroundColor = "green";
    } else {
      pumpStateSpan.textContent = "DETENIDA";
      pumpStateSpan.style.color = "gray";
      pumpIndicator.style.backgroundColor = "gray";
    }
  }
}

function publishMessage(topic, payload) {
  if (client && client.isConnected()) {
    const message = new Paho.MQTT.Message(payload);
    message.destinationName = topic;
    client.send(message);
    console.log("Publicado:", topic, "=", payload);
  } else {
    console.warn("Cliente MQTT no conectado");
  }
}

// --- Eventos botones ---
startPumpBtn.addEventListener("click", () => publishMessage(TOPIC_PUMP_CMD_START, "ON"));
stopPumpBtn.addEventListener("click", () => publishMessage(TOPIC_PUMP_CMD_STOP, "ON"));

// --- Inicia conexión ---
window.onload = connectMQTT;
