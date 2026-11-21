import { api } from '../api.js';
import { bindStoreFilter, meterList, rangeSelect, stat } from '../components.js';
import { state } from '../state.js';
import { $, esc, formatDate } from '../util.js';

export async function loadAttempts() {
  const a = await api(`/attempts?days=${state.rangeDays}`);
  const root = $('#view-attempts');
  const sum = (rows) => rows.reduce((total, row) => total + row.count, 0);

  const recent = a.recent.length
    ? a.recent.map((r) => `
        <tr>
          <td>${esc(formatDate(r.at))}</td>
          <td>${esc(r.session_id)}</td>
          <td>${r.outcome}</td>
          <td>${esc(r.reason || '—')}</td>
          <td>${r.attempt_no}</td>
        </tr>`).join('')
    : '<tr><td colspan="5" class="empty-inline">No payment attempts in this period.</td></tr>';

  root.innerHTML = `${rangeSelect()}
    <div class="stats">
      ${stat('Attempts', a.total, '', 'card')}
      ${stat('Declined', a.declined, '', 'x-circle', 'warn')}
      ${stat('Errors', a.error, 'gateway / connectivity issues', 'target', 'danger')}
      ${stat('Recovered', a.recovered, 'declined, then paid on a later try', 'check-circle', 'ok')}
    </div>
    <div class="card"><h2>Decline reasons (${state.rangeDays}d)</h2><p class="sub">Why the processor declined the card</p>${meterList(a.by_reason, sum(a.by_reason) || 1)}</div>
    <div class="card">
      <h2>Recent attempts</h2>
      <div class="table-wrap"><table>
        <thead><tr><th>Time</th><th>Session</th><th>Outcome</th><th>Reason</th><th>#</th></tr></thead>
        <tbody>${recent}</tbody>
      </table></div>
    </div>`;

  const storeSelect = $('[data-role=store-filter]', root);
  if (storeSelect) bindStoreFilter(storeSelect, loadAttempts);
  $('[data-role=range]', root).addEventListener('change', (e) => {
    state.rangeDays = Number(e.target.value);
    loadAttempts();
  });
}
