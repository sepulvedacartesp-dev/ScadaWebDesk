// --- Configuración MQTT ---
const MQTT_HOST = "550bffa3b80b4956be6a94fdcd65b4d1.s1.eu.hivemq.cloud";
const MQTT_PORT = 8884;
const MQTT_PATH = "/mqtt";
const MQTT_USERNAME = "Webclient";
const MQTT_PASSWORD = "Webclient2025";
const CLIENT_ID = "web_scada_" + Math.random().toString(16).substr(2, 8);

// Tópicos - Sistema 1
const TOPIC_LEVEL_READ_1 = "PLC/Nivel";
const TOPIC_PUMP_STATE_READ_1 = "PLC/PumpSts";
const TOPIC_PUMP_CMD_START_1 = "PLC/PumpCmdStart";
const TOPIC_PUMP_CMD_STOP_1  = "PLC/PumpCmdStop";

// Tópicos - Sistema 2 (Nuevos tópicos)
const TOPIC_LEVEL_READ_2 = "Micro/Nivel2";
const TOPIC_PUMP_STATE_READ_2 = "Micro/PumpSts2";
const TOPIC_PUMP_CMD_START_2 = "Micro/PumpCmdStart2";
const TOPIC_PUMP_CMD_STOP_2  = "Micro/PumpCmdStop2";

// --- Elementos HTML - Sistema 1 ---
const tankLevelDiv = document.getElementById("tank-level");
const levelValueSpan = document.getElementById("level-value");
const pumpStateSpan = document.getElementById("pump-state");
const pumpIndicator = document.getElementById("pump-indicator");
const startPumpBtn = document.getElementById("start-pump-btn");
const stopPumpBtn = document.getElementById("stop-pump-btn");

// --- Elementos HTML - Sistema 2 (Nuevos elementos) ---
const tankLevelDiv2 = document.getElementById("tank-level-2");
const levelValueSpan2 = document.getElementById("level-value-2");
const pumpStateSpan2 = document.getElementById("pump-state-2");
const pumpIndicator2 = document.getElementById("pump-indicator-2");
const startPumpBtn2 = document.getElementById("start-pump-btn-2");
const stopPumpBtn2 = document.getElementById("stop-pump-btn-2");

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
  // Suscribirse a los tópicos del sistema 1
  client.subscribe(TOPIC_LEVEL_READ_1);
  client.subscribe(TOPIC_PUMP_STATE_READ_1);
  // Suscribirse a los tópicos del sistema 2
  client.subscribe(TOPIC_LEVEL_READ_2);
  client.subscribe(TOPIC_PUMP_STATE_READ_2);
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

  // Lógica para el Sistema 1
  if (message.destinationName === TOPIC_LEVEL_READ_1) {
    let level = parseFloat(message.payloadString);
    if (!isNaN(level)) {
      level = Math.max(0, Math.min(100, level));
      tankLevelDiv.style.height = level + "%";
      levelValueSpan.textContent = level.toFixed(0);
    }
  }

  if (message.destinationName === TOPIC_PUMP_STATE_READ_1) {
    let state;
    try {
      state = JSON.parse(message.payloadString.toLowerCase());
    } catch {
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

  // Lógica para el Sistema 2 (Nueva lógica)
  if (message.destinationName === TOPIC_LEVEL_READ_2) {
    let level = parseFloat(message.payloadString);
    if (!isNaN(level)) {
      level = Math.max(0, Math.min(100, level));
      tankLevelDiv2.style.height = level + "%";
      levelValueSpan2.textContent = level.toFixed(0);
    }
  }

  if (message.destinationName === TOPIC_PUMP_STATE_READ_2) {
    let state;
    try {
      state = JSON.parse(message.payloadString.toLowerCase());
    } catch {
      state = message.payloadString === "1";
    }

    if (state === true) {
      pumpStateSpan2.textContent = "ENCENDIDA";
      pumpStateSpan2.style.color = "green";
      pumpIndicator2.style.backgroundColor = "green";
    } else {
      pumpStateSpan2.textContent = "DETENIDA";
      pumpStateSpan2.style.color = "gray";
      pumpIndicator2.style.backgroundColor = "gray";
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

// --- Eventos botones - Sistema 1 ---
startPumpBtn.addEventListener("click", () => publishMessage(TOPIC_PUMP_CMD_START_1, "ON"));
stopPumpBtn.addEventListener("click", () => publishMessage(TOPIC_PUMP_CMD_STOP_1, "ON"));

// --- Eventos botones - Sistema 2 (Nuevos eventos) ---
startPumpBtn2.addEventListener("click", () => publishMessage(TOPIC_PUMP_CMD_START_2, "ON"));
stopPumpBtn2.addEventListener("click", () => publishMessage(TOPIC_PUMP_CMD_STOP_2, "ON"));

// --- Inicia conexión ---
window.onload = connectMQTT;