import { api } from '../api.js';
import { barChart, rangeSelect, stat } from '../components.js';
import { refreshCounts } from '../counts.js';
import { state } from '../state.js';
import { $, TZ_OFFSET, esc, money } from '../util.js';

export async function loadRevenue() {
  const [, r] = await Promise.all([refreshCounts(), api(`/revenue?days=${state.rangeDays}&tz=${TZ_OFFSET}`)]);
  const fmt = (n) => money(n, r.currency);
  const root = $('#view-revenue');
  const maxMethod = Math.max(...r.by_method.map((m) => m.amount), 1);

  const methods = r.by_method.length
    ? r.by_method.map((m) => `
        <div class="meter-row">
          <div class="top"><span>${esc(m.label)}</span><span>${fmt(m.amount)} · ${m.orders} ${m.orders === 1 ? 'order' : 'orders'}</span></div>
          <div class="meter"><i style="width:${(m.amount / maxMethod) * 100}%"></i></div>
        </div>`).join('')
    : '<p class="empty-inline">No paid orders yet.</p>';

  root.innerHTML = `${rangeSelect()}
    <div class="stats">
      ${stat('Today', fmt(r.today), '', 'dollar')}
      ${stat('Last 7 days', fmt(r.last7), '', 'trending', 'info')}
      ${stat('Last 30 days', fmt(r.last30), '', 'trending', 'info')}
      ${stat('All time', fmt(r.all_time), '', 'target', 'ok')}
    </div>
    <div class="stats">
      ${stat(`Revenue (${state.rangeDays}d)`, fmt(r.period_total), `${r.period_orders} paid orders`, 'receipt')}
      ${stat('Average order', fmt(r.avg_order), '', 'card')}
      ${stat('Awaiting payment', fmt(r.awaiting_payment), `${r.awaiting_count} pending orders`, 'clock', 'warn')}
      ${stat('Refunded', fmt(r.refunded), `${r.refunded_count} orders`, 'x-circle', 'danger')}
    </div>
    <div class="card"><div class="card-head"><div><h2>Daily revenue</h2><p class="sub" style="margin:0">Counted on the day each order was marked paid</p></div></div>${barChart(r.daily, 'amount', fmt)}</div>
    <div class="card"><h2>By payment method</h2><p class="sub">All time</p>${methods}</div>
    <p class="muted" style="font-size:13px">Shown in ${esc(r.currency)}${r.excluded_other_currency ? ` (${r.excluded_other_currency} order(s) in other currencies excluded)` : ''}. Refunded orders are excluded.</p>`;

  $('[data-role=range]', root).addEventListener('change', (e) => {
    state.rangeDays = Number(e.target.value);
    loadRevenue();
  });
}
