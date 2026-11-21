import { api } from '../api.js';
import { bindStoreFilter, rangeSelect } from '../components.js';
import { state } from '../state.js';
import { $, esc, money } from '../util.js';

export async function loadAttribution() {
  const a = await api(`/attribution?days=${state.rangeDays}`);
  const root = $('#view-attribution');
  const fmt = (n) => money(n, a.currency);

  const rows = a.rows.length
    ? a.rows.map((r) => `
        <tr>
          <td>${esc(r.campaign)}</td>
          <td>${r.sessions}</td>
          <td>${r.viewed}</td>
          <td>${r.orders}</td>
          <td>${fmt(r.revenue)}</td>
          <td>${r.conversion}%</td>
        </tr>`).join('')
    : '<tr><td colspan="6" class="empty-inline">No sessions in this period.</td></tr>';

  root.innerHTML = `${rangeSelect()}
    <div class="card">
      <h2>Campaigns</h2>
      <p class="sub">Sessions grouped by UTM campaign (sessions created without one show as "(none)")</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Campaign</th><th>Sessions</th><th>Viewed</th><th>Orders</th><th>Revenue</th><th>Conv.</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>
    <p class="muted" style="font-size:13px">Attribution is first-wins: the first ad click or UTM link that brings a customer to checkout is credited, even if they come back later through another link.</p>`;

  const storeSelect = $('[data-role=store-filter]', root);
  if (storeSelect) bindStoreFilter(storeSelect, loadAttribution);
  $('[data-role=range]', root).addEventListener('change', (e) => {
    state.rangeDays = Number(e.target.value);
    loadAttribution();
  });
}
