// --- Configuración MQTT ---
const MQTT_HOST = "550bffa3b80b4956be6a94fdcd65b4d1.s1.eu.hivemq.cloud";
const MQTT_PORT = 8884;
const MQTT_PATH = "/mqtt";
const MQTT_USERNAME = "Webclient";
const MQTT_PASSWORD = "Webclient2025";
const CLIENT_ID = "web_scada_" + Math.random().toString(16).substr(2, 8);

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

let config;
let client;
let currentView = 'matrix';
let currentRole = 'anonimo';
let usersData = null; // Variable para almacenar los usuarios del archivo JSON

const topicStateCache = {};
const topicElementMap = {};
let containerElements = [];

function loadConfigAndRender() {
    // Cargar los usuarios desde el archivo JSON
    fetch('users.json')
        .then(response => response.json())
        .then(data => {
            usersData = data.users;
            // Cargar el resto de la configuración solo después de cargar los usuarios
            if (matrixBtn && sidebarBtn) {
                matrixBtn.addEventListener('click', () => renderView('matrix'));
                sidebarBtn.addEventListener('click', () => renderView('sidebar'));
            }

            loginBtn.addEventListener('click', () => loginModal.style.display = 'block');
            closeBtn.addEventListener('click', () => loginModal.style.display = 'none');
            window.addEventListener('click', (e) => {
                if (e.target === loginModal) {
                    loginModal.style.display = 'none';
                }
            });

            loginForm.addEventListener('submit', handleLogin);
            
            const savedUser = localStorage.getItem('currentUser');
            const savedRole = localStorage.getItem('currentRole');
            if (savedUser && savedRole) {
                currentUserSpan.textContent = savedUser;
                currentRole = savedRole;
                applyAccessControl();
            }

            config = JSON.parse(localStorage.getItem('scadaConfig'));
            if (!config || config.containers.length === 0) {
                scadaContainer.innerHTML = '<p>No hay configuración guardada. Por favor, ve a la página de <a href="config.html">configuración</a> para generar una.</p>';
                return;
            }
            
            if (mainTitleH1 && config && config.mainTitle) {
                mainTitleH1.textContent = config.mainTitle;
            }

            renderAllContainers();
            renderView('matrix');
            connectMQTT();
        })
        .catch(error => {
            console.error('Error al cargar la base de datos de usuarios:', error);
            loginError.textContent = 'No se pudo cargar la base de datos de usuarios.';
        });
}

function handleLogin(e) {
    e.preventDefault();
    const username = usernameInput.value;
    const password = passwordInput.value;

    if (!usersData) {
        loginError.textContent = 'Base de datos de usuarios no disponible.';
        return;
    }

    const user = usersData.find(u => u.username === username && u.password === password);

    if (user) {
        currentUserSpan.textContent = user.username;
        currentRole = user.role;
        localStorage.setItem('currentUser', user.username);
        localStorage.setItem('currentRole', user.role);
        loginModal.style.display = 'none';
        loginError.textContent = '';
        applyAccessControl();
    } else {
        loginError.textContent = 'Usuario o contraseña incorrectos.';
    }
}

function applyAccessControl() {
    if (configLink) {
        configLink.style.display = (currentRole === 'admin') ? 'block' : 'none';
    }

    const controlButtons = scadaContainer.querySelectorAll('.controls .btn');
    controlButtons.forEach(btn => {
        if (currentRole === 'visualizacion') {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
        } else {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        }
    });
}

function renderAllContainers() {
    if (sidebarMenu) {
        sidebarMenu.innerHTML = '';
        config.containers.forEach((containerData, index) => {
            const link = document.createElement('a');
            link.href = '#';
            link.textContent = containerData.title;
            link.onclick = (e) => {
                e.preventDefault();
                renderSingleContainerView(index);
            };
            sidebarMenu.appendChild(link);
        });
    }

    scadaContainer.innerHTML = '';
    containerElements = [];
    config.containers.forEach((containerData, containerIndex) => {
        const container = createContainerElement(containerData, containerIndex);
        containerElements.push(container);
        scadaContainer.appendChild(container);
    });

    applyAccessControl();
}

function createContainerElement(containerData, containerIndex) {
    const container = document.createElement('div');
    container.className = 'system-container';
    container.dataset.containerIndex = containerIndex;

    const title = document.createElement('h2');
    title.textContent = containerData.title;
    container.appendChild(title);
    
    const controlsDiv = document.createElement('div');
    controlsDiv.className = 'controls';
    
    containerData.objects.forEach((obj, objIndex) => {
        let element;
        const elementId = `container-${containerIndex}-obj-${objIndex}`;
        const topic = obj.topic;

        if (topic) {
             if (!topicElementMap[topic]) {
                topicElementMap[topic] = [];
            }
        }

        switch (obj.type) {
            case 'level':
                container.innerHTML += `
                    <div class="tank-container">
                        <div id="${elementId}" class="tank-level"></div>
                    </div>
                    <div class="level-indicator">${obj.label || 'Nivel'}: <span id="${elementId}-value">0</span>%</div>
                `;
                topicElementMap[topic].push({ id: elementId, type: 'level', color: obj.color });
                break;
            case 'pumpStatus':
                container.innerHTML += `<div class="pump-status"><div id="${elementId}" class="pump-indicator"></div><span id="${elementId}-state">${obj.label || 'Bomba'}</span></div>`;
                topicElementMap[topic].push({ id: elementId, type: 'pumpStatus', onColor: obj.onColor, offColor: obj.offColor });
                break;
            case 'motorSpeed':
                container.innerHTML += `<div class="motor-speed">${obj.label || 'Velocidad'}: <span id="${elementId}">0</span> RPM</div>`;
                topicElementMap[topic].push({ id: elementId, type: 'motorSpeed' });
                break;
            case 'startBtn':
                element = document.createElement('button');
                element.className = 'btn btn-start';
                element.textContent = obj.label;
                element.style.backgroundColor = obj.color;
                element.addEventListener('click', () => publishMessage(topic, 'ON'));
                controlsDiv.appendChild(element);
                break;
            case 'stopBtn':
                element = document.createElement('button');
                element.className = 'btn btn-stop';
                element.textContent = obj.label;
                element.style.backgroundColor = obj.color;
                element.addEventListener('click', () => publishMessage(topic, 'OFF'));
                controlsDiv.appendChild(element);
                break;
            case 'resetBtn':
                element = document.createElement('button');
                element.className = 'btn btn-reset';
                element.textContent = obj.label;
                element.style.backgroundColor = obj.color;
                element.addEventListener('click', () => publishMessage(topic, 'RESET'));
                controlsDiv.appendChild(element);
                break;
            case 'gauge':
                container.innerHTML += `
                    <div class="gauge-container">
                        <div class="gauge-dial">
                            <div id="${elementId}" class="gauge-fill" style="background-color: ${obj.color};"></div>
                            <div class="gauge-center"></div>
                        </div>
                        <div class="gauge-label">${obj.label || 'Gauge'}</div>
                        <div id="${elementId}-value" class="gauge-value">0%</div>
                    </div>
                `;
                topicElementMap[topic].push({ id: elementId, type: 'gauge', color: obj.color });
                break;
            case 'number':
                container.innerHTML += `<div class="number-indicator">${obj.label || 'Valor'}: <span id="${elementId}">0</span></div>`;
                topicElementMap[topic].push({ id: elementId, type: 'number' });
                break;
        }
    });

    if (controlsDiv.children.length > 0) {
        container.appendChild(controlsDiv);
    }
    
    return container;
}


function renderView(viewType) {
    currentView = viewType;

    if (matrixBtn) matrixBtn.classList.toggle('active', viewType === 'matrix');
    if (sidebarBtn) sidebarBtn.classList.toggle('active', viewType === 'sidebar');

    if (sidebarMenu) sidebarMenu.style.display = viewType === 'sidebar' ? 'flex' : 'none';

    if (scadaContainer) {
        if (viewType === 'matrix') {
            scadaContainer.classList.add('matrix-view');
            scadaContainer.classList.remove('sidebar-view');
            containerElements.forEach(el => el.style.display = 'block');
        } else {
            scadaContainer.classList.add('sidebar-view');
            scadaContainer.classList.remove('matrix-view');
            renderSingleContainerView(0);
        }
    }
    
    applyCachedValues();
}

function renderSingleContainerView(index) {
    containerElements.forEach(el => el.style.display = 'none');
    if (containerElements[index]) {
        containerElements[index].style.display = 'block';
    }

    if (sidebarMenu) {
        const activeLink = sidebarMenu.querySelector('.active');
        if (activeLink) {
            activeLink.classList.remove('active');
        }
        if (sidebarMenu.children[index]) {
            sidebarMenu.children[index].classList.add('active');
        }
    }
}


function updateElement(target, payload) {
  const element = document.getElementById(target.id);
  if (!element) return;

  switch (target.type) {
    case 'level':
      const level = parseFloat(payload) || 0;
      const valueSpan = document.getElementById(`${target.id}-value`);
      element.style.height = level + "%";
      element.style.backgroundColor = target.color;
      if (valueSpan) valueSpan.textContent = level.toFixed(0);
      break;
    case 'pumpStatus':
      const state = (payload.toLowerCase() === 'true' || payload === '1');
      const stateSpan = document.getElementById(`${target.id}-state`);
      if (state) {
        element.style.backgroundColor = target.onColor || 'green';
        if (stateSpan) {
            stateSpan.textContent = 'ENCENDIDA';
            stateSpan.style.color = target.onColor || 'green';
        }
      } else {
        element.style.backgroundColor = target.offColor || 'gray';
        if (stateSpan) {
            stateSpan.textContent = 'DETENIDA';
            stateSpan.style.color = target.offColor || 'gray';
        }
      }
      break;
    case 'motorSpeed':
    case 'number':
      const value = parseFloat(payload) || 0;
      element.textContent = value.toFixed(0);
      break;
    case 'gauge':
        const gaugeLevel = parseFloat(payload) || 0;
        const gaugeValueSpan = document.getElementById(`${target.id}-value`);
        const angle = (gaugeLevel / 100) * 180;
        element.style.transform = `rotate(${angle}deg)`;
        if (gaugeValueSpan) gaugeValueSpan.textContent = `${gaugeLevel.toFixed(0)}%`;
        break;
  }
}

function applyCachedValues() {
  for (const topic in topicElementMap) {
    if (topicStateCache[topic] !== undefined) {
      const payload = topicStateCache[topic];
      topicElementMap[topic].forEach(target => {
        updateElement(target, payload);
      });
    }
  }
}

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
  client.connect(options);
}

function onConnectSuccess() {
  console.log("Conectado al broker MQTT");
  if (connectStatusSpan) {
    connectStatusSpan.textContent = 'Conectado';
    connectStatusSpan.style.color = 'green';
  }

  const topicsToSubscribe = new Set();
  if (config) {
      config.containers.forEach(container => {
        container.objects.forEach(obj => {
          if (obj.topic && obj.type !== 'startBtn' && obj.type !== 'stopBtn' && obj.type !== 'resetBtn') {
            topicsToSubscribe.add(obj.topic);
          }
        });
      });
  }

  topicsToSubscribe.forEach(topic => {
    client.subscribe(topic);
    console.log("Suscrito a tópico:", topic);
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
    console.log("Publicado:", topic, "=", payload);
  } else {
    console.warn("Cliente MQTT no conectado");
  }
}

document.addEventListener('DOMContentLoaded', loadConfigAndRender);