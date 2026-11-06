import { api } from '../api.js';
import { barChart, meterList, rangeSelect, stat } from '../components.js';
import { refreshCounts } from '../counts.js';
import { state } from '../state.js';
import { $, TZ_OFFSET } from '../util.js';

export async function loadVisits() {
  const [, v] = await Promise.all([refreshCounts(), api(`/visits?days=${state.rangeDays}&tz=${TZ_OFFSET}`)]);
  const f = v.funnel;
  const sum = (rows) => rows.reduce((total, row) => total + row.count, 0);
  const root = $('#view-visits');

  root.innerHTML = `${rangeSelect()}
    <div class="stats">
      ${stat('Checkout page views', v.views, '', 'eye')}
      ${stat('Unique visitors', v.visitors, '', 'users', 'info')}
      ${stat('Sessions created', f.created, 'carts sent from your store', 'package')}
      ${stat('Viewed checkout', f.viewed, '', 'eye', 'info')}
      ${stat('Placed order', f.ordered, '', 'check-circle', 'ok')}
      ${stat('Conversion', `${f.conversion}%`, 'orders ÷ viewed', 'target', 'ok')}
    </div>
    <div class="card"><div class="card-head"><div><h2>Daily views</h2><p class="sub" style="margin:0">Checkout page opens per day</p></div></div>${barChart(v.daily, 'views', (n) => `${n} views`)}</div>
    <div class="two">
      <div class="card"><h2>Devices</h2><p class="sub">What customers check out on</p>${meterList(v.devices, sum(v.devices))}</div>
      <div class="card"><h2>Referrers</h2><p class="sub">Where they came from</p>${meterList(v.referrers, sum(v.referrers))}</div>
    </div>
    <p class="muted" style="font-size:13px">Views are counted when a customer opens a checkout link (reloads within 10 minutes and bots are ignored). Visitors are counted from a salted hash of IP + browser; no raw IPs are stored. Referrer is the page they came from, when the browser shares it.</p>`;

  $('[data-role=range]', root).addEventListener('change', (e) => {
    state.rangeDays = Number(e.target.value);
    loadVisits();
  });
}
