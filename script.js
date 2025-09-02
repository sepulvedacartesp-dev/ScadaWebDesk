// --- Configuración MQTT ---
const MQTT_HOST = "550bffa3b80b4956be6a94fdcd65b4d1.s1.eu.hivemq.cloud";
const MQTT_PORT = 8884;
const MQTT_PATH = "/mqtt";
const MQTT_USERNAME = "Webclient";
const MQTT_PASSWORD = "Webclient2025";
const CLIENT_ID = "web_scada_" + Math.random().toString(16).substr(2, 8);
const JSONBIN_URL = "https://api.jsonbin.io/v3/b/68b5b95aae596e708fdefd2b";
const JSONBIN_MASTER_KEY = "$2a$10$T0EWIyZETjULNG0RGtMVMeMnFoAfw5boBuqMUP66b3CYzyGJilPE."; // Clave Maestra

const scadaContainer = document.getElementById('scada-container');
const sidebarMenu = document.getElementById('sidebar-menu');
const matrixBtn = document.getElementById('view-matrix');
const sidebarBtn = document.getElementById('view-sidebar');
const connectStatusSpan = document.getElementById('connect-status');
const mainTitleH1 = document.getElementById('main-title');
const loginBtn = document.getElementById('login-btn');
const logoutBtn = document.getElementById('logout-btn');
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
let usersData = null;

const topicStateCache = {};
const topicElementMap = {};
let containerElements = [];

function loadConfigAndRender() {
    fetch('scada_config.json')
    .then(response => {
        if (!response.ok) {
            console.warn('scada_config.json no encontrado, cargando desde localStorage...');
            const savedConfig = localStorage.getItem('scadaConfig');
            if (savedConfig) {
                config = JSON.parse(savedConfig);
                initializeUI();
            } else {
                scadaContainer.innerHTML = '<p>No hay configuración guardada. Por favor, ve a la página de <a href="config.html">configuración</a> para generar una.</p>';
            }
        } else {
            return response.json();
        }
    })
    .then(data => {
        if (data) {
            config = data;
            localStorage.setItem('scadaConfig', JSON.stringify(config));
            initializeUI();
        }
    })
    .catch(error => {
        console.error('Error al cargar la configuración:', error);
        scadaContainer.innerHTML = '<p>Error al cargar la configuración.</p>';
    });

    fetch(JSONBIN_URL, {
        headers: {
            'X-Master-Key': '$2a$10$T0EWIyZETjULNG0RGtMVMeMnFoAfw5boBuqMUP66b3CYzyGJilPE.'
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Error al cargar la base de datos de usuarios desde JSONBin.io');
        }
        return response.json();
    })
    .then(data => {
        usersData = data.record.users;
        console.log("Usuarios cargados exitosamente desde JSONBin.io.");
        setupEventListeners();
        checkIfLoggedIn(); // Reemplazado por esta llamada para manejar el estado de inicio de sesión inicial
    })
    .catch(error => {
        console.error('Error al cargar la base de datos de usuarios:', error);
        loginError.textContent = 'No se pudo cargar la base de datos de usuarios.';
    });
}

function initializeUI() {
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
}

function setupEventListeners() {
    if (matrixBtn && sidebarBtn) {
        matrixBtn.addEventListener('click', () => renderView('matrix'));
        sidebarBtn.addEventListener('click', () => renderView('sidebar'));
    }
    loginBtn.addEventListener('click', () => loginModal.style.display = 'block');
    logoutBtn.addEventListener('click', handleLogout);
    closeBtn.addEventListener('click', () => {
        loginModal.style.display = 'none';
        loginError.textContent = '';
        loginForm.reset();
    });
    window.addEventListener('click', (e) => {
        if (e.target === loginModal) {
            loginModal.style.display = 'none';
            loginError.textContent = '';
            loginForm.reset();
        }
    });
    loginForm.addEventListener('submit', handleLogin);
}

// Nueva función para verificar el estado de inicio de sesión y actualizar la interfaz de usuario
function checkIfLoggedIn() {
    const savedUser = localStorage.getItem('currentUser');
    const savedRole = localStorage.getItem('currentRole');
    if (savedUser && savedRole) {
        currentUserSpan.textContent = savedUser;
        currentRole = savedRole;
        loginBtn.style.display = 'none';
        logoutBtn.style.display = 'inline-block';
    } else {
        currentUserSpan.textContent = 'Anónimo';
        currentRole = 'anonimo';
        loginBtn.style.display = 'inline-block';
        logoutBtn.style.display = 'none';
    }
    updateUIForRole(); // Llama a la función de control de acceso
}

function handleLogin(e) {
  e.preventDefault();
  const username = usernameInput.value;
  const password = passwordInput.value;

  if (!usersData) {
      loginError.textContent = 'Base de datos de usuarios no disponible.';
      return;
  }

  const user = usersData.find(u => u.username === username);

  if (user) {
      const hashedPassword = CryptoJS.SHA256(password).toString(CryptoJS.enc.Hex);
      
      if (hashedPassword === user.password) {
          currentUserSpan.textContent = user.username;
          currentRole = user.role;
          localStorage.setItem('currentUser', user.username);
          localStorage.setItem('currentRole', user.role);

          // --- ESTA ES LA CORRECCIÓN ---
          // Llama a la función de control de acceso inmediatamente después de un login exitoso.
          updateUIForRole();
          // -----------------------------

          loginModal.style.display = 'none';
          loginError.textContent = '';
      } else {
          loginError.textContent = 'Usuario o contraseña incorrectos.';
      }
  } else {
      loginError.textContent = 'Usuario o contraseña incorrectos.';
  }
}

function handleLogout() {
    localStorage.removeItem('currentUser');
    localStorage.removeItem('currentRole');
    currentUserSpan.textContent = 'Anónimo';
    currentRole = 'anonimo';
    updateUIForRole();
}

// Corregido: La función `updateUIForRole` ahora maneja toda la lógica de control de acceso
function updateUIForRole() {
    // Controla la visibilidad de los botones de control (Start, Stop, Reset)
    const isControlRole = (currentRole === 'admin' || currentRole === 'operador');
    document.querySelectorAll('.btn-start, .btn-stop, .btn-reset').forEach(btn => {
        btn.disabled = !isControlRole;
        btn.style.opacity = isControlRole ? '1' : '0.5';
        btn.style.cursor = isControlRole ? 'pointer' : 'not-allowed';
    });

    // Controla la visibilidad del enlace de configuración
    if (configLink) {
        configLink.style.display = (currentRole === 'admin') ? 'inline-block' : 'none';
    }

    // Controla la visibilidad de los botones de login y logout
    if (loginBtn && logoutBtn) {
        loginBtn.style.display = (currentRole === 'anonimo') ? 'inline-block' : 'none';
        logoutBtn.style.display = (currentRole !== 'anonimo') ? 'inline-block' : 'none';
    }
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

    updateUIForRole(); // Llama a la función después de renderizar los elementos
}

function renderSingleContainerView(index) {
    if (containerElements.length > 0) {
        containerElements.forEach((container, i) => {
            container.style.display = (i === index) ? 'flex' : 'none';
        });
        matrixBtn.classList.remove('active');
        sidebarBtn.classList.add('active');
        sidebarMenu.style.display = 'flex';
    }
}

function renderView(view) {
    currentView = view;
    if (currentView === 'matrix') {
        matrixBtn.classList.add('active');
        sidebarBtn.classList.remove('active');
        scadaContainer.classList.remove('sidebar-view');
        scadaContainer.classList.add('matrix-view');
        sidebarMenu.style.display = 'none';

        containerElements.forEach(el => {
            el.style.display = 'flex';
        });

    } else if (currentView === 'sidebar') {
        matrixBtn.classList.remove('active');
        sidebarBtn.classList.add('active');
        scadaContainer.classList.remove('matrix-view');
        scadaContainer.classList.add('sidebar-view');
        sidebarMenu.style.display = 'flex';

        containerElements.forEach(el => {
            el.style.display = 'none';
        });
    }
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
        const unit = obj.unit || '';
        if (topic) {
            if (!topicElementMap[topic]) {
                topicElementMap[topic] = [];
            }
        }

        switch (obj.type) {
            case 'level':
                element = createLevelIndicator(elementId, obj.label, unit, obj.color);
                break;
            case 'pumpStatus':
                element = createPumpStatus(elementId, obj.label, obj.onColor, obj.offColor);
                break;
            case 'motorSpeed':
                element = createMotorSpeed(elementId, obj.label, unit);
                break;
            case 'startBtn':
                element = createButton(obj.label, 'btn-start', topic, 'ON', obj.color);
                break;
            case 'stopBtn':
                element = createButton(obj.label, 'btn-stop', topic, 'OFF', obj.color);
                break;
            case 'resetBtn':
                element = createButton(obj.label, 'btn-reset', topic, 'RESET', obj.color);
                break;
            case 'gauge':
                element = createGauge(elementId, obj.label, unit, obj.min, obj.max, obj.color);
                break;
            case 'number':
                element = createNumberIndicator(elementId, obj.label, unit);
                break;
            case 'text':
                element = createTextIndicator(elementId, obj.label);
                break;
            default:
                return;
        }

        if (element) {
            if (element.element) {
                container.appendChild(element.element);
            } else if (element.type === 'button') {
                controlsDiv.appendChild(element.element);
            }
            if (topic && element.update) {
                topicElementMap[topic].push(element);
            }
        }
    });

    if (controlsDiv.children.length > 0) {
        container.appendChild(controlsDiv);
    }
    
    // Add event listeners for new elements after they are appended
    const startBtns = container.querySelectorAll('.btn-start');
    const stopBtns = container.querySelectorAll('.btn-stop');
    const resetBtns = container.querySelectorAll('.btn-reset');
    
    startBtns.forEach(btn => {
        const topic = btn.getAttribute('data-topic');
        const payload = btn.getAttribute('data-payload');
        btn.addEventListener('click', () => publishMessage(topic, payload));
    });
    stopBtns.forEach(btn => {
        const topic = btn.getAttribute('data-topic');
        const payload = btn.getAttribute('data-payload');
        btn.addEventListener('click', () => publishMessage(topic, payload));
    });
    resetBtns.forEach(btn => {
        const topic = btn.getAttribute('data-topic');
        const payload = btn.getAttribute('data-payload');
        btn.addEventListener('click', () => publishMessage(topic, payload));
    });

    return container;
}


function createLevelIndicator(id, label, unit, color) {
    const div = document.createElement('div');
    div.classList.add('tank-container');
    div.style.border = `2px solid ${color}`;
    const tankLevel = document.createElement('div');
    tankLevel.id = id;
    tankLevel.classList.add('tank-level');
    tankLevel.style.backgroundColor = color;
    div.appendChild(tankLevel);
    const indicator = document.createElement('p');
    indicator.classList.add('level-indicator');
    indicator.innerHTML = `<span>${label || 'Nivel'}:</span> <span id="${id}-value" class="value">0</span> ${unit}`;
    div.appendChild(indicator);
    return { element: div, update: (value) => {
        const percentage = Math.max(0, Math.min(100, parseFloat(value)));
        document.getElementById(id).style.height = `${percentage}%`;
        document.getElementById(`${id}-value`).textContent = percentage.toFixed(1);
    }};
}


function createPumpStatus(id, label, onColor, offColor) {
    const div = document.createElement('div');
    div.classList.add('pump-status');
    const indicator = document.createElement('span');
    indicator.id = id;
    indicator.classList.add('pump-indicator');
    indicator.style.backgroundColor = offColor;
    const text = document.createElement('span');
    text.id = `${id}-state`;
    text.textContent = label;
    div.appendChild(indicator);
    div.appendChild(text);
    return { element: div, update: (value) => {
      const indicatorEl = document.getElementById(id);
      const textEl = document.getElementById(`${id}-state`);
      
      // Convertir el valor a booleano si es una cadena
      let is_on = false;
      if (typeof value === 'string') {
          is_on = value.toUpperCase() === 'ON' || value === '1' || value.toLowerCase() === 'true';
      } else if (typeof value === 'boolean') {
          is_on = value;
      }
  
      if (is_on) {
          indicatorEl.style.backgroundColor = onColor;
          textEl.textContent = `${label} ON`;
      } else {
          indicatorEl.style.backgroundColor = offColor;
          textEl.textContent = `${label} OFF`;
      }
  }};
}

function createMotorSpeed(id, label, unit) {
    const div = document.createElement('div');
    div.classList.add('motor-speed');
    div.innerHTML = `<span>${label}:</span> <span id="${id}">0</span> ${unit}`;
    return { element: div, update: (value) => {
        document.getElementById(id).textContent = parseFloat(value).toFixed(1);
    }};
}


function createButton(label, className, topic, payload, color) {
    const button = document.createElement('button');
    button.classList.add('btn', className);
    button.textContent = label;
    button.style.backgroundColor = color;
    button.setAttribute('data-topic', topic);
    button.setAttribute('data-payload', payload);
    return { element: button, type: 'button' };
}

function createGauge(id, label, unit, min, max, color) {
    const div = document.createElement('div');
    div.classList.add('gauge-container');
    div.style.setProperty('--gauge-color', color);
    
    const dial = document.createElement('div');
    dial.classList.add('gauge-dial');
    const fill = document.createElement('div');
    fill.id = id;
    fill.classList.add('gauge-fill');
    dial.appendChild(fill);
    
    const center = document.createElement('div');
    center.classList.add('gauge-center');
    
    const valueSpan = document.createElement('div');
    valueSpan.id = `${id}-value`;
    valueSpan.classList.add('gauge-value');
    
    const labelSpan = document.createElement('div');
    labelSpan.classList.add('gauge-label');
    labelSpan.textContent = `${label} (${unit})`;
    
    div.appendChild(dial);
    div.appendChild(center);
    div.appendChild(labelSpan);
    div.appendChild(valueSpan);

    return { element: div, update: (value) => {
        const numericValue = parseFloat(value);
        if (!isNaN(numericValue)) {
            const clampedValue = Math.max(min, Math.min(max, numericValue));
            const angle = (clampedValue - min) / (max - min) * 180;
            document.getElementById(id).style.transform = `rotate(${angle}deg)`;
            document.getElementById(`${id}-value`).textContent = numericValue.toFixed(1);
        }
    }};
}

function createNumberIndicator(id, label, unit) {
    const div = document.createElement('div');
    div.classList.add('number-indicator');
    div.innerHTML = `<span>${label}:</span> <span id="${id}" class="value">0</span> ${unit}`;
    return { element: div, update: (value) => {
        document.getElementById(id).textContent = parseFloat(value).toFixed(2);
    }};
}

function createTextIndicator(id, label) {
    const div = document.createElement('div');
    div.classList.add('text-indicator');
    div.innerHTML = `<span>${label}:</span> <span id="${id}" class="value"></span>`;
    return { element: div, update: (value) => {
        document.getElementById(id).textContent = value;
    }};
}


function connectMQTT() {
    if (connectStatusSpan) {
        connectStatusSpan.textContent = 'Conectando...';
        connectStatusSpan.style.color = 'orange';
    }

    client = new Paho.MQTT.Client(MQTT_HOST, MQTT_PORT, MQTT_PATH, CLIENT_ID);
    client.onConnectionLost = onConnectionLost;
    client.onMessageArrived = onMessageArrived;

    const options = {
        timeout: 3,
        userName: MQTT_USERNAME,
        password: MQTT_PASSWORD,
        useSSL: true,
        onSuccess: onConnectSuccess,
        onFailure: onConnectFailure
    };
    client.connect(options);
}

function onConnectSuccess() {
    console.log("Conexión exitosa a MQTT");
    if (connectStatusSpan) {
        connectStatusSpan.textContent = 'Conectado';
        connectStatusSpan.style.color = 'green';
    }
    subscribeToTopics();
}

function subscribeToTopics() {
  if (client && client.isConnected()) {
    const uniqueTopics = new Set(Object.keys(topicElementMap));
    uniqueTopics.forEach(topic => {
      client.subscribe(topic);
      console.log("Suscrito al tópico:", topic);
    });
  }
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
    console.log("Mensaje publicado:", topic, payload);
  } else {
    console.error("Cliente MQTT no conectado. No se puede publicar el mensaje.");
  }
}

function updateElement(target, payload) {
    if (typeof target.update === 'function') {
        target.update(payload);
    }
}

window.onload = loadConfigAndRender;