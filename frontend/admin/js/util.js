// Small DOM and formatting helpers shared by every view.
import { icon } from '/static/shared/icons.js';

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
/** Escapes text for safe interpolation into HTML. Use it for every server-provided value. */
export const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ESCAPES[c]);

export const money = (minorUnits, currency) => {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(minorUnits / 100);
  } catch {
    return `${(minorUnits / 100).toFixed(2)} ${currency}`;
  }
};

export const formatDate = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—');
export const formatDay = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' }) : '—');

export const badge = (value) => `<span class="badge b-${esc(value)}">${esc(value)}</span>`;

/** Fills every `[data-icon="name"]` element under `root` with its SVG. */
export function hydrateIcons(root = document) {
  $$('[data-icon]', root).forEach((el) => { el.innerHTML = icon(el.dataset.icon); });
}

// ---------------------------------------------------------------- avatars
export const initials = (name) => (String(name ?? '').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('') || '?').toUpperCase();
export const avatarClass = (name) => {
  let hash = 0;
  for (const ch of String(name ?? '')) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `av-${hash % 6}`;
};
export const avatar = (name) => `<span class="avatar ${avatarClass(name)}">${esc(initials(name))}</span>`;

// ---------------------------------------------------------------- feedback
/** Short-lived notification in the corner. */
export function toast(text, ok = true) {
  const host = $('#toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast ${ok ? '' : 'err'}`;
  el.innerHTML = `<span class="ti">${icon(ok ? 'check-circle' : 'x-circle')}</span><span>${esc(text)}</span>`;
  host.append(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 260); }, ok ? 2600 : 4500);
}

/** Shows a result both inline (in a `.msg` element, if given) and as a toast. */
export function flash(element, ok, text) {
  if (element) {
    element.className = `msg ${ok ? 'ok' : 'err'}`;
    element.textContent = text;
  }
  toast(text, ok);
}

/** Minutes behind UTC, sent to the API so "today" and daily buckets use the admin's local days. */
export const TZ_OFFSET = new Date().getTimezoneOffset();

export const ORDER_STATUSES = ['pending', 'processing', 'shipped', 'completed', 'cancelled', 'refunded'];
export const PAYMENT_STATUSES = ['pending', 'paid', 'failed', 'refunded'];

/** Shows the store name and, when a logo URL is set, the logo image in the sidebar (otherwise the first letter). */
export function applyBrand(name, logoUrl = '') {
  const mark = $('#logo');
  const url = /^https?:\/\//i.test(logoUrl.trim()) ? logoUrl.trim() : '';
  $('#brand').textContent = name;
  mark.closest('.brand-row').classList.toggle('has-logo', Boolean(url));
  if (url) {
    const img = document.createElement('img');
    img.src = url;
    img.alt = name;
    img.referrerPolicy = 'no-referrer';
    mark.replaceChildren(img);
  } else {
    mark.textContent = name.trim()[0]?.toUpperCase() || 'C';
  }
}
