// --- Configuración MQTT ---
const MQTT_HOST = "550bffa3b80b4956be6a94fdcd65b4d1.s1.eu.hivemq.cloud";
const MQTT_PORT = 8884;
const MQTT_PATH = "/mqtt";
const MQTT_USERNAME = "Webclient";
const MQTT_PASSWORD = "Webclient2025";
const CLIENT_ID = "web_scada_" + Math.random().toString(16).substr(2, 8);

// --- Referencias a elementos del DOM ---
const scadaContainer = document.getElementById('scada-container');
const sidebarMenu = document.getElementById('sidebar-menu');
const matrixBtn = document.getElementById('view-matrix');
const sidebarBtn = document.getElementById('view-sidebar');
const connectStatusSpan = document.getElementById('connect-status');
const mainTitleH1 = document.getElementById('main-title');
const loginBtn = document.getElementById('login-btn');
const configLink = document.getElementById('config-link');
const currentUserSpan = document.getElementById('current-user');
const loginModal = document.getElementById('login-modal');
const closeBtn = document.querySelector('.close-btn');
const loginForm = document.getElementById('login-form');
const usernameInput = document.getElementById('username-input');
const passwordInput = document.getElementById('password-input');
const loginError = document.getElementById('login-error');

let usersData = [];
let config;
let client;
let currentView = 'matrix';
let currentRole = 'anonimo';
let currentUser = 'anonimo';

const topicStateCache = {};
const topicElementMap = {};

// --- URL de la base de datos de usuarios en JSONBin.io ---
const JSONBIN_URL = "https://api.jsonbin.io/v3/b/68b5b95aae596e708fdefd2b"; // <-- REEMPLAZA CON TU BIN ID

// --- Funciones de Carga de Configuración y Autenticación ---

function loadConfigAndRender() {
    let storedConfig = localStorage.getItem('scadaConfig');
    if (storedConfig) {
        config = JSON.parse(storedConfig);
        renderConfig(config);
    } else {
        alert("No se encontró configuración. Por favor, vaya a la página de configuración.");
        return;
    }

    // Carga los usuarios desde JSONBin.io
    fetch(JSONBIN_URL)
        .then(response => {
            if (!response.ok) {
                throw new Error('Error al cargar la base de datos de usuarios');
            }
            return response.json();
        })
        .then(data => {
            usersData = data.record.users;
            console.log("Usuarios cargados exitosamente.");
        })
        .catch(error => {
            console.error('Error al cargar la base de datos de usuarios:', error);
            loginError.textContent = 'Error al cargar la base de datos de usuarios.';
        });
}

// --- Funciones de Renderizado ---

function renderConfig(config) {
    scadaContainer.innerHTML = '';
    sidebarMenu.innerHTML = '';
    topicElementMap = {};

    config.containers.forEach(container => {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'system-group';
        groupDiv.id = `group-${container.id}`;
        scadaContainer.appendChild(groupDiv);

        if (currentView === 'sidebar') {
            const sidebarItem = document.createElement('div');
            sidebarItem.className = 'sidebar-item';
            sidebarItem.textContent = container.name;
            sidebarItem.onclick = () => {
                const visibleGroup = document.querySelector('.system-group.active');
                if (visibleGroup) {
                    visibleGroup.classList.remove('active');
                }
                groupDiv.classList.add('active');
            };
            sidebarMenu.appendChild(sidebarItem);
        }

        container.topics.forEach(topic => {
            const topicDiv = createTopicElement(topic, container.id);
            groupDiv.appendChild(topicDiv);
            if (!topicElementMap[topic.topic]) {
                topicElementMap[topic.topic] = [];
            }
            topicElementMap[topic.topic].push(topicDiv);
        });
    });

    if (currentView === 'matrix') {
        scadaContainer.classList.remove('sidebar-view');
        scadaContainer.classList.add('matrix-view');
        sidebarMenu.style.display = 'none';
    } else {
        scadaContainer.classList.remove('matrix-view');
        scadaContainer.classList.add('sidebar-view');
        sidebarMenu.style.display = 'flex';
        const firstGroup = scadaContainer.querySelector('.system-group');
        if (firstGroup) {
            firstGroup.classList.add('active');
        }
    }
}

function createTopicElement(topic, containerId) {
    const topicDiv = document.createElement('div');
    topicDiv.className = 'topic-container';
    topicDiv.dataset.containerId = containerId;
    topicDiv.dataset.topicType = topic.type;
    topicDiv.dataset.topic = topic.topic;

    const nameSpan = document.createElement('span');
    nameSpan.className = 'topic-name';
    nameSpan.textContent = topic.name;
    topicDiv.appendChild(nameSpan);

    const valueSpan = document.createElement('span');
    valueSpan.className = 'topic-value';
    valueSpan.textContent = topic.initialValue || 'N/A';
    topicDiv.appendChild(valueSpan);

    if (topic.type === 'control') {
        const controlDiv = document.createElement('div');
        controlDiv.className = 'topic-control';

        if (topic.controlType === 'button') {
            const controlBtn = document.createElement('button');
            controlBtn.className = 'btn';
            controlBtn.textContent = 'Toggle';
            controlBtn.onclick = () => {
                const currentState = topicStateCache[topic.topic] === '1' ? '0' : '1';
                publishMessage(topic.topic, currentState);
            };
            controlDiv.appendChild(controlBtn);
        } else if (topic.controlType === 'slider') {
            const sliderInput = document.createElement('input');
            sliderInput.type = 'range';
            sliderInput.min = 0;
            sliderInput.max = 100;
            sliderInput.value = 0;
            const sliderValueSpan = document.createElement('span');
            sliderValueSpan.textContent = sliderInput.value;
            sliderInput.oninput = () => {
                sliderValueSpan.textContent = sliderInput.value;
            };
            sliderInput.onchange = () => {
                publishMessage(topic.topic, sliderInput.value);
            };
            controlDiv.appendChild(sliderInput);
            controlDiv.appendChild(sliderValueSpan);
        }

        topicDiv.appendChild(controlDiv);
    }

    return topicDiv;
}

function updateElement(element, value) {
    const type = element.dataset.topicType;
    const valueSpan = element.querySelector('.topic-value');

    if (type === 'state') {
        valueSpan.textContent = value === '1' ? 'ON' : 'OFF';
        element.style.backgroundColor = value === '1' ? '#d4edda' : '#f8d7da';
        element.style.borderColor = value === '1' ? '#c3e6cb' : '#f5c6cb';
    } else {
        valueSpan.textContent = value;
    }
}

// --- Funciones de Eventos ---

matrixBtn.addEventListener('click', () => {
    currentView = 'matrix';
    matrixBtn.classList.add('active');
    sidebarBtn.classList.remove('active');
    renderConfig(config);
});

sidebarBtn.addEventListener('click', () => {
    currentView = 'sidebar';
    sidebarBtn.classList.add('active');
    matrixBtn.classList.remove('active');
    renderConfig(config);
});

loginBtn.addEventListener('click', () => {
    loginModal.style.display = 'block';
});

closeBtn.addEventListener('click', () => {
    loginModal.style.display = 'none';
});

window.addEventListener('click', (event) => {
    if (event.target === loginModal) {
        loginModal.style.display = 'none';
    }
});

loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const username = usernameInput.value;
    const password = passwordInput.value;
    const user = usersData.find(u => u.username === username);

    if (user) {
        // Hashear la contraseña ingresada por el usuario
        const hashedPassword = CryptoJS.SHA256(password).toString(CryptoJS.enc.Hex);

        // Comparar el hash de la contraseña ingresada con el hash guardado
        if (hashedPassword === user.password) {
            currentUser = username;
            currentRole = user.role;
            loginModal.style.display = 'none';
            updateUI();
            connectMQTT();
        } else {
            loginError.textContent = 'Usuario o contraseña incorrectos.';
        }
    } else {
        loginError.textContent = 'Usuario o contraseña incorrectos.';
    }
});

// --- Funciones de UI ---

function updateUI() {
    currentUserSpan.textContent = currentUser;
    if (currentRole === 'admin' || currentRole === 'operador') {
        configLink.style.display = 'inline-block';
    } else {
        configLink.style.display = 'none';
    }
}

// --- Funciones MQTT ---

function connectMQTT() {
    if (client && client.isConnected()) {
        client.disconnect();
    }

    client = new Paho.MQTT.Client(MQTT_HOST, MQTT_PORT, MQTT_PATH, CLIENT_ID);
    client.onConnectionLost = onConnectionLost;
    client.onMessageArrived = onMessageArrived;

    const options = {
        onSuccess: onConnectSuccess,
        onFailure: onConnectFailure,
        useSSL: true,
        userName: MQTT_USERNAME,
        password: MQTT_PASSWORD
    };

    try {
        client.connect(options);
    } catch (error) {
        console.error("Error de conexión:", error);
    }
}

function onConnectSuccess() {
    console.log("Conectado exitosamente al broker MQTT");
    if (connectStatusSpan) {
        connectStatusSpan.textContent = 'Conectado';
        connectStatusSpan.style.color = 'green';
    }

    // Suscribirse a los tópicos de configuración
    config.containers.forEach(container => {
        container.topics.forEach(topic => {
            console.log("Suscribiendo a tópico:", topic.topic);
            client.subscribe(topic.topic);
        });
    });
}

function onConnectFailure(responseObject) {
    console.error("Fallo la conexión:", responseObject.errorMessage);
    if (connectStatusSpan) {
        connectStatusSpan.textContent = 'Fallo de Conexión';
        connectStatusSpan.style.color = 'red';
    }
}

function onConnectionLost(responseObject) {
    if (responseObject.errorCode !== 0) {
        console.log("Conexión perdida:", responseObject.errorMessage);
        if (connectStatusSpan) {
            connectStatusSpan.textContent = 'Conexión Perdida';
            connectStatusSpan.style.color = 'orange';
        }
    }
    setTimeout(connectMQTT, 5000);
}

function onMessageArrived(message) {
    topicStateCache[message.destinationName] = message.payloadString;
    const targets = topicElementMap[message.destinationName];
    if (targets) {
        targets.forEach(target => {
            updateElement(target, message.payloadString);
        });
    }
}

function publishMessage(topic, payload) {
    if (currentRole === 'visualizacion') {
        console.warn("Permiso denegado. Rol de visualización no puede publicar.");
        return;
    }
    if (client && client.isConnected()) {
        const message = new Paho.MQTT.Message(payload);
        message.destinationName = topic;
        client.send(message);
        console.log(`Mensaje publicado en ${topic}: ${payload}`);
    } else {
        console.error("No se puede publicar: el cliente MQTT no está conectado.");
    }
}

// --- Inicio de la Aplicación ---
document.addEventListener('DOMContentLoaded', loadConfigAndRender);