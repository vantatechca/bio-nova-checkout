// Admin entry point: sign-in, tab navigation, theme and view dispatch.
import { api, isSignedIn, login, logout, setUnauthorizedHandler } from './api.js';
import { state } from './state.js';
import { $, $$, hydrateIcons } from './util.js';
import { loadEmail } from './views/email.js';
import { ORDER_TABS, initOrdersView, loadOrders } from './views/orders.js';
import { loadRevenue } from './views/revenue.js';
import { loadSettings } from './views/settings.js';
import { loadVisits } from './views/visits.js';

const VIEWS = ['orders', 'revenue', 'email', 'visits', 'settings'];
const LOADERS = { revenue: loadRevenue, email: loadEmail, visits: loadVisits, settings: loadSettings };
const TITLES = {
  pending: ['Pending orders', 'Awaiting payment. Zelle, Interac and bank orders stay here until you mark them paid.'],
  paid: ['Paid orders', 'Orders with payment received.'],
  failed: ['Failed & cancelled', 'Cancelled orders, failed payments and refunds.'],
  revenue: ['Revenue', 'Money in, by day and by payment method.'],
  visits: ['Visits', 'How customers move through your checkout.'],
  email: ['Email', 'Customer notifications and the delivery log.'],
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
async function loadBrand() {
  try {
    const { storeName } = await api('/settings');
    $('#brand').textContent = storeName;
    const letter = storeName.trim()[0]?.toUpperCase() || 'C';
    $('#logo').textContent = letter;
    $('#login-logo').textContent = letter;
  } catch { /* the sign-in handler deals with auth errors */ }
}

function render() {
  const signedIn = isSignedIn();
  $('#login').classList.toggle('hide', signedIn);
  $('#shell').classList.toggle('hide', !signedIn);
  if (signedIn) {
    loadBrand();
    navigate(state.tab);
  }
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

render();
