import { icon } from '/static/shared/icons.js';
import { api } from '../api.js';
import { bindStoreFilter } from '../components.js';
import { state } from '../state.js';
import { $, $$, esc, formatDate, hydrateIcons, money } from '../util.js';

const STEP_LABELS = {
  form_started: 'Started form',
  contact_done: 'Entered contact',
  address_done: 'Entered address',
  method_chosen: 'Chose payment',
  card_entered: 'Entered card',
  pay_clicked: 'Clicked Pay',
};
const KIND_ICONS = { session: 'package', visit: 'eye', step: 'check', payment: 'card', order: 'receipt', email: 'mail' };

let rows = [];

export async function loadAbandoned() {
  const root = $('#view-abandoned');
  const hours = state.abandonedHours ?? 6;
  const data = await api(`/sessions/abandoned?hours=${hours}`);
  rows = data.rows;

  root.innerHTML = `
    <div class="toolbar-range">
      <select data-role="store-filter" aria-label="Filter by store"></select>
      <select data-role="hours" aria-label="Idle for at least">
        ${[1, 3, 6, 12, 24, 72].map((h) => `<option value="${h}" ${h === hours ? 'selected' : ''}>Idle ${h >= 24 ? `${h / 24}d` : `${h}h`}+</option>`).join('')}
      </select>
    </div>
    <div class="card flush">
      <div class="table-wrap"><table>
        <thead><tr><th>Started</th><th>Customer</th><th>Total</th><th>Got to</th><th>Steps reached</th><th></th></tr></thead>
        <tbody id="abandoned-body"></tbody>
      </table></div>
      ${rows.length ? '' : '<div class="empty-inline">No abandoned checkouts in this window.</div>'}
    </div>
    <p class="muted" style="font-size:13px">A checkout counts as abandoned once it has sat open, without being completed, for at least this long.</p>`;

  $('#abandoned-body').innerHTML = rows
    .map(
      (r, i) => `
      <tr>
        <td>${esc(formatDate(r.created_at))}</td>
        <td>${esc(r.customer_name || '(no name yet)')}${r.customer_email ? `<br><small>${esc(r.customer_email)}</small>` : ''}</td>
        <td>${money(r.total, r.currency)}</td>
        <td>${r.viewed_at ? 'Viewed' : 'Never opened'}</td>
        <td>${r.steps.length ? r.steps.map((s) => esc(STEP_LABELS[s] ?? s)).join(', ') : '—'}</td>
        <td><button class="small" data-timeline="${i}">${icon('clock')} Timeline</button></td>
      </tr>`,
    )
    .join('');

  $$('[data-timeline]').forEach((btn) =>
    btn.addEventListener('click', () => openTimeline(rows[Number(btn.dataset.timeline)])),
  );

  const storeSelect = $('[data-role=store-filter]', root);
  if (storeSelect) bindStoreFilter(storeSelect, loadAbandoned);
  $('[data-role=hours]', root).addEventListener('change', (e) => {
    state.abandonedHours = Number(e.target.value);
    loadAbandoned();
  });
}

async function openTimeline(session) {
  const drawer = $('#drawer');
  drawer.innerHTML = `
    <div class="drawer-head">
      <div><h2>Checkout timeline</h2><div class="meta"><span>${esc(session.customer_name || session.id)}</span></div></div>
      <button class="icon-only" data-role="close" aria-label="Close"><span data-icon="x"></span></button>
    </div>
    <div class="drawer-body"><div class="block"><ol class="timeline" id="timeline-items"><li>Loading…</li></ol></div></div>`;
  hydrateIcons(drawer);
  $('#overlay').classList.remove('hide');
  $('[data-role=close]', drawer).addEventListener('click', () => $('#overlay').classList.add('hide'));

  const items = await api(`/sessions/${session.id}/timeline`);
  $('#timeline-items').innerHTML = items
    .map(
      (it) => `<li>${icon(KIND_ICONS[it.kind] ?? 'package')} <b>${esc(it.text)}</b><small>${esc(formatDate(it.at))}</small></li>`,
    )
    .join('');
  hydrateIcons(drawer);
}
