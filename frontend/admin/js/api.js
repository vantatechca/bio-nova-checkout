// Thin client for the admin API. Owns the auth token and reports expiry to the app.

const TOKEN_KEY = 'checkout-admin-token';
import { state } from './state.js';

let token = sessionStorage.getItem(TOKEN_KEY);
let onUnauthorized = () => {};

export const isSignedIn = () => Boolean(token);
export const setUnauthorizedHandler = (handler) => { onUnauthorized = handler; };

export function setToken(value) {
  token = value;
  if (value) sessionStorage.setItem(TOKEN_KEY, value);
  else sessionStorage.removeItem(TOKEN_KEY);
}

// Endpoints whose data is per store. Reads may span all stores; settings-style calls always need one store.
const FILTERED = ['/orders', '/stats', '/revenue', '/visits'];
const PER_STORE = ['/settings', '/card', '/shopify', '/test-session'];

function scoped(path) {
  const base = path.split('?')[0];
  const matches = (list) => list.some((p) => base === p || base.startsWith(`${p}/`));
  let store = null;
  if (matches(FILTERED)) store = state.store;
  else if (matches(PER_STORE)) store = state.settingsStore ?? state.store ?? state.stores[0]?.id ?? null;
  if (store === null) return path;
  return `${path}${path.includes('?') ? '&' : '?'}store=${store}`;
}

/** Calls `/api/admin<path>`; throws an Error carrying the server's message on failure. */
export async function api(path, { method = 'GET', body } = {}) {
  const response = await fetch(`/api/admin${scoped(path)}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401 && path !== '/login') {
    onUnauthorized();
    throw new Error('Session expired');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

export async function login(password) {
  const { token: issued } = await api('/login', { method: 'POST', body: { password } });
  setToken(issued);
}

export function logout() {
  if (token) api('/logout', { method: 'POST' }).catch(() => {});
  setToken(null);
}
