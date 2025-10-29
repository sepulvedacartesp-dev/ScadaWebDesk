const DEFAULT_BASE_URL = "https://scadawebdesk.onrender.com";

let baseUrl = DEFAULT_BASE_URL;
let customTokenProvider = null;

/**
 * Permite configurar una URL base distinta (testing/local).
 * @param {string} url
 */
export function setBaseUrl(url) {
  if (!url) return;
  baseUrl = String(url).replace(/\/+$/, "");
}

/**
 * Permite inyectar un proveedor de tokens alternativo.
 * @param {() => Promise<string>} provider
 */
export function setTokenProvider(provider) {
  if (typeof provider === "function") {
    customTokenProvider = provider;
  }
}

async function getFirebaseIdToken(forceRefresh = false) {
  if (customTokenProvider) {
    return customTokenProvider(forceRefresh);
  }
  const firebaseApp = window.firebase;
  if (!firebaseApp || typeof firebaseApp.auth !== "function") {
    throw new Error("Firebase no inicializado en esta pagina");
  }
  const auth = firebaseApp.auth();
  const user = auth.currentUser;
  if (user) {
    return user.getIdToken(forceRefresh);
  }
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      unsubscribe();
      reject(new Error("Usuario no autenticado"));
    }, 10000);
    const unsubscribe = auth.onAuthStateChanged(
      (next) => {
        clearTimeout(timer);
        unsubscribe();
        if (next) {
          next.getIdToken(forceRefresh).then(resolve).catch(reject);
        } else {
          reject(new Error("Usuario no autenticado"));
        }
      },
      (error) => {
        clearTimeout(timer);
        unsubscribe();
        reject(error);
      }
    );
  });
}

async function authFetch(path, { method = "GET", headers = {}, body, query } = {}) {
  const token = await getFirebaseIdToken();
  const mergedHeaders = new Headers(headers);
  mergedHeaders.set("Authorization", `Bearer ${token}`);
  if (body && !mergedHeaders.has("Content-Type")) {
    mergedHeaders.set("Content-Type", "application/json");
  }
  const url = buildUrl(path, query);
  const response = await fetch(url, {
    method,
    headers: mergedHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    throw createHttpError(response, errorText);
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function buildUrl(path, query) {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(baseUrl + normalized);
  if (query && typeof query === "object") {
    Object.entries(query).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      if (Array.isArray(value)) {
        value.forEach((item) => url.searchParams.append(key, item));
      } else {
        url.searchParams.set(key, value);
      }
    });
  }
  return url.toString();
}

function createHttpError(response, rawBody) {
  let detail = rawBody;
  try {
    const parsed = JSON.parse(rawBody);
    if (parsed && typeof parsed.detail !== "undefined") {
      detail = parsed.detail;
    } else {
      detail = parsed;
    }
  } catch (_) {
    /* keep raw body */
  }
  const error = new Error(typeof detail === "string" ? detail : "Solicitud HTTP fallida");
  error.status = response.status;
  error.statusText = response.statusText;
  error.body = detail;
  return error;
}

// ---- Catálogo ----

export async function fetchQuoteCatalog({ includeInactive = false } = {}) {
  const data = await authFetch("/api/quote-catalog", {
    query: includeInactive ? { include_inactive: "true" } : undefined,
  });
  return Array.isArray(data?.items) ? data.items : [];
}

export async function upsertCatalog(payload) {
  return authFetch("/api/quote-catalog", {
    method: "PUT",
    body: payload,
  });
}

export async function deleteCatalogItem(itemId) {
  if (!itemId) throw new Error("itemId es requerido");
  return authFetch(`/api/quote-catalog/items/${encodeURIComponent(itemId)}`, {
    method: "DELETE",
  });
}

// ---- Cotizaciones ----

export async function listQuotes({ page = 1, pageSize = 20, filters = {}, empresaId } = {}) {
  const query = {
    page,
    page_size: pageSize,
  };
  if (empresaId) query.empresa_id = empresaId;
  const {
    estados,
    search,
    clienteRut,
    preparedBy,
    quoteNumber,
    createdFrom,
    createdTo,
  } = filters;
  if (Array.isArray(estados) && estados.length) query.estados = estados;
  if (search) query.search = search;
  if (clienteRut) query.clienteRut = clienteRut;
  if (preparedBy) query.preparedBy = preparedBy;
  if (quoteNumber) query.quote_number = quoteNumber;
  if (createdFrom) query.createdFrom = createdFrom;
  if (createdTo) query.createdTo = createdTo;
  return authFetch("/api/quotes", { query });
}

export async function getQuote(quoteId, { empresaId } = {}) {
  if (!quoteId) throw new Error("quoteId requerido");
  return authFetch(`/api/quotes/${encodeURIComponent(quoteId)}`, {
    query: empresaId ? { empresa_id: empresaId } : undefined,
  });
}

export async function createQuote(payload, { empresaId } = {}) {
  const query = empresaId ? { empresa_id: empresaId } : undefined;
  return authFetch("/api/quotes", {
    method: "POST",
    body: payload,
    query,
  });
}

export async function updateQuote(quoteId, payload, { empresaId } = {}) {
  if (!quoteId) throw new Error("quoteId requerido");
  const query = empresaId ? { empresa_id: empresaId } : undefined;
  return authFetch(`/api/quotes/${encodeURIComponent(quoteId)}`, {
    method: "PUT",
    body: payload,
    query,
  });
}

export async function changeQuoteStatus(quoteId, { estado, descripcion }, { empresaId } = {}) {
  if (!quoteId) throw new Error("quoteId requerido");
  if (!estado) throw new Error("estado es requerido");
  const query = empresaId ? { empresa_id: empresaId } : undefined;
  return authFetch(`/api/quotes/${encodeURIComponent(quoteId)}/status`, {
    method: "PATCH",
    body: { estado, descripcion },
    query,
  });
}

export async function logQuotePdfDownload(quoteId, { empresaId } = {}) {
  if (!quoteId) throw new Error("quoteId requerido");
  const query = empresaId ? { empresa_id: empresaId } : undefined;
  return authFetch(`/api/quotes/${encodeURIComponent(quoteId)}/events/pdf`, {
    method: "POST",
    query,
  });
}

// ---- Clientes ----

export async function listClients({ query: searchTerm, limit = 10, empresaId } = {}) {
  const query = {
    limit,
  };
  if (searchTerm) query.q = searchTerm;
  if (empresaId) query.empresa_id = empresaId;
  const response = await authFetch("/api/clients", { query });
  return Array.isArray(response?.results) ? response.results : [];
}

export async function createClient(payload, { empresaId } = {}) {
  const query = empresaId ? { empresa_id: empresaId } : undefined;
  return authFetch("/api/clients", {
    method: "POST",
    body: payload,
    query,
  });
}

// ---- Utilidades ----

export async function ensureToken(forceRefresh = false) {
  return getFirebaseIdToken(forceRefresh);
}

export function resetApiConfig() {
  baseUrl = DEFAULT_BASE_URL;
  customTokenProvider = null;
}
