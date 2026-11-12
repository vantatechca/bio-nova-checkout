// Stores tab: every storefront connected to this checkout.
import { icon } from '/static/shared/icons.js';
import { api } from '../api.js';
import { refreshCounts } from '../counts.js';
import { state } from '../state.js';
import { $, $$, esc, flash, hydrateIcons } from '../util.js';

/** Set by main.js: re-reads the stores, updates the switcher and (optionally) opens one's settings. */
let hooks = { reload: async () => {}, open: () => {} };
export const bindStoreHooks = (value) => { hooks = value; };

const pill = (cls, text) => `<span class="badge b-${cls}">${text}</span>`;

export async function loadStores() {
  state.stores = await api('/stores');
  refreshCounts();
  const root = $('#view-stores');
  root.innerHTML = `
    <div class="card flush">
      <div class="table-wrap"><table>
        <thead><tr><th>Store</th><th>Website / Shopify</th><th>Card</th><th>Orders</th><th>Status</th><th></th></tr></thead>
        <tbody>${state.stores.map((s) => `
          <tr>
            <td><div class="order-no">${esc(s.name)}<small>#${s.id} · ${esc(s.slug)}</small></div></td>
            <td><div class="nm">${esc(s.store_url || '—')}<small>${esc(s.shopify_domain || 'Shopify not connected')}</small></div></td>
            <td>${s.card_ready ? pill('paid', 'ready') : pill('pending', 'not set up')}</td>
            <td><span class="money">${s.orders}</span></td>
            <td>${s.active ? pill('completed', 'active') : pill('cancelled', 'disabled')}</td>
            <td style="white-space:nowrap">
              <button class="small" data-open="${s.id}">${icon('sliders')} Settings</button>
              <button class="small" data-toggle="${s.id}">${s.active ? 'Disable' : 'Enable'}</button>
              <button class="small danger" data-del="${s.id}">Delete</button>
            </td>
          </tr>`).join('')}</tbody>
      </table></div>
    </div>
    <div class="card"><h2>Add a store</h2>
      <p class="sub">Each store gets its own API key, branding, payment setup and webhook. Orders and visits stay separate.</p>
      <form id="store-add" style="display:flex;gap:10px;flex-wrap:wrap">
        <input id="store-name" placeholder="Store name, e.g. Bionova Club" maxlength="100" required style="flex:1;min-width:220px;margin:0">
        <button class="primary">${icon('check')} Add store</button>
      </form>
      <span class="msg" id="store-msg"></span>
    </div>`;
  hydrateIcons(root);

  $('#store-add', root).addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const created = await api('/stores', { method: 'POST', body: { name: $('#store-name', root).value.trim() } });
      await hooks.reload();
      hooks.open(created.id); // straight to its settings: that's where the Shopify link and card setup go
    } catch (err) { flash($('#store-msg', root), false, err.message); }
  });
  $$('[data-open]', root).forEach((b) => b.addEventListener('click', () => hooks.open(Number(b.dataset.open))));
  $$('[data-toggle]', root).forEach((b) => b.addEventListener('click', async () => {
    const store = state.stores.find((s) => s.id === Number(b.dataset.toggle));
    try {
      await api(`/stores/${store.id}`, { method: 'PATCH', body: { active: !store.active } });
      await hooks.reload();
      await loadStores();
    } catch (err) { flash($('#store-msg', root), false, err.message); }
  }));
  $$('[data-del]', root).forEach((b) => b.addEventListener('click', async () => {
    const store = state.stores.find((s) => s.id === Number(b.dataset.del));
    if (!confirm(`Delete “${store.name}”? This can't be undone.`)) return;
    try {
      await api(`/stores/${store.id}`, { method: 'DELETE' });
      if (state.store === store.id) state.store = null;
      await hooks.reload();
      await loadStores();
    } catch (err) { flash($('#store-msg', root), false, err.message); }
  }));
}
