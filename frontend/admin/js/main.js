// Admin entry point: sign-in, tab navigation, theme and view dispatch.
import { api, isSignedIn, login, logout, setUnauthorizedHandler } from './api.js';
import { state } from './state.js';
import { $, $$, applyBrand, hydrateIcons } from './util.js';
import { loadEmail } from './views/email.js';
import { ORDER_TABS, initOrdersView, loadOrders } from './views/orders.js';
import { loadRevenue } from './views/revenue.js';
import { loadSettings } from './views/settings.js';
import { bindStoreHooks, loadStores } from './views/stores.js';
import { loadVisits } from './views/visits.js';

const VIEWS = ['orders', 'revenue', 'email', 'visits', 'stores', 'settings'];
const LOADERS = { revenue: loadRevenue, email: loadEmail, visits: loadVisits, stores: loadStores, settings: loadSettings };
const TITLES = {
  pending: ['Pending orders', 'Awaiting payment. Orders stay here until their payment is confirmed.'],
  paid: ['Paid orders', 'Orders with payment received.'],
  failed: ['Failed & cancelled', 'Cancelled orders, failed payments and refunds.'],
  revenue: ['Revenue', 'Money in, by day and by payment method.'],
  visits: ['Visits', 'How customers move through your checkout.'],
  email: ['Email', 'Customer notifications and the delivery log.'],
  stores: ['Stores', 'Every storefront connected to this checkout.'],
  settings: ['Settings & API', 'Connect your store and configure checkout.'],
};

// ---------------------------------------------------------------- theme
function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  const dark = theme === 'dark' || (!theme && matchMedia('(prefers-color-scheme: dark)').matches);
  $('#theme-toggle .ico').dataset.icon = dark ? 'sun' : 'moon';
  $('#theme-toggle .t').textContent = dark ? 'Light mode' : 'Dark mode';
  hydrateIcons($('#theme-toggle'));
}
function toggleTheme() {
  const dark = document.documentElement.dataset.theme === 'dark'
    || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  const next = dark ? 'light' : 'dark';
  try { localStorage.setItem('checkout-theme', next); } catch { /* storage unavailable */ }
  applyTheme(next);
}

// ---------------------------------------------------------------- mobile menu
const setMenu = (open) => {
  $('#sidebar').classList.toggle('open', open);
  $('#scrim').classList.toggle('hide', !open);
};

// ---------------------------------------------------------------- navigation
const selectedStore = () => state.stores.find((x) => x.id === state.store) ?? null;

/** The sidebar brand is the first active store; the orders/revenue/visits filter does not change it. */
/** The sign-in page shows the store's logo too; it needs no login, so this reads the public brand. */
async function loadLoginBrand() {
  try {
    const brand = await (await fetch('/api/public/brand')).json();
    const mark = $('#login-logo');
    const url = /^https?:\/\//i.test(brand.logo_url ?? '') ? brand.logo_url.trim() : '';
    if (url) {
      const img = document.createElement('img');
      img.src = url;
      img.alt = brand.name;
      img.referrerPolicy = 'no-referrer';
      mark.classList.add('has-img');
      mark.replaceChildren(img);
    } else {
      mark.textContent = brand.name.trim()[0]?.toUpperCase() || 'C';
    }
  } catch { /* keep the default mark */ }
}

function showBrand() {
  const store = state.stores.find((x) => x.active) ?? state.stores[0];
  if (!store) return;
  applyBrand(store.name, store.logo_url ?? '');
}

/** Re-reads the store list (after adding / disabling / deleting one) and refreshes the switcher and brand. */
async function reloadStores() {
  state.stores = await api('/stores');
  if (state.store !== null && !selectedStore()) state.store = null;
  if (state.settingsStore !== null && !state.stores.some((x) => x.id === state.settingsStore)) state.settingsStore = null;
  showBrand();
}

async function loadBrand() {
  try {
    await reloadStores();
    let saved = null;
    try { saved = Number(localStorage.getItem('checkout-store')) || null; } catch { /* storage unavailable */ }
    if (saved && state.stores.some((x) => x.id === saved)) state.store = saved;
  } catch { /* the sign-in handler deals with auth errors */ }
}

function render() {
  const signedIn = isSignedIn();
  $('#login').classList.toggle('hide', signedIn);
  $('#shell').classList.toggle('hide', !signedIn);
  if (signedIn) loadBrand().finally(() => navigate(state.tab));
}

function navigate(tab) {
  state.tab = tab;
  const activeView = ORDER_TABS.includes(tab) ? 'orders' : tab;
  const [title, sub] = TITLES[tab];
  $('#page-title').textContent = title;
  $('#page-sub').textContent = sub;
  document.title = `${title} · Order Admin`;
  $$('.tab').forEach((button) => button.classList.toggle('on', button.dataset.tab === tab));
  for (const name of VIEWS) $(`#view-${name}`).classList.toggle('hide', name !== activeView);
  setMenu(false);
  (LOADERS[tab] ?? loadOrders)().catch((err) => {
    if (isSignedIn()) alert(err.message);
  });
}

function signOut() {
  logout();
  render();
}

hydrateIcons();
applyTheme(document.documentElement.dataset.theme);
setUnauthorizedHandler(signOut);
initOrdersView();

$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('#login-error').textContent = '';
  try {
    await login($('#password').value);
    $('#password').value = '';
    render();
  } catch (err) {
    $('#login-error').textContent = err.message;
  }
});
$('#sign-out').addEventListener('click', signOut);
$('#theme-toggle').addEventListener('click', toggleTheme);
$('#menu').addEventListener('click', () => setMenu(true));
$('#scrim').addEventListener('click', () => setMenu(false));
$$('.tab').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.tab)));
bindStoreHooks({
  reload: reloadStores,
  open: (id) => { state.settingsStore = id; navigate('settings'); },
});

loadLoginBrand();
render();
