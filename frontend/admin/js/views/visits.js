import { api } from '../api.js';
import { barChart, bindStoreFilter, meterList, rangeSelect, stat } from '../components.js';
import { refreshCounts } from '../counts.js';
import { state } from '../state.js';
import { $, TZ_OFFSET, esc, formatDate, flash } from '../util.js';

const STEP_LABELS = {
  form_started: 'Started the form',
  contact_done: 'Entered contact info',
  address_done: 'Entered shipping address',
  method_chosen: 'Chose a payment method',
  card_entered: 'Entered card details',
  pay_clicked: 'Clicked Pay',
};

/** The step funnel as a list of bars, with the biggest single-step drop-off called out. */
function stepFunnelHtml(steps) {
  if (!steps.length || !steps[0].count) return '<p class="empty-inline">No checkout activity yet.</p>';
  const max = steps[0].count;
  let worst = { i: -1, drop: 0 };
  steps.forEach((s, i) => {
    if (i === 0) return;
    const drop = steps[i - 1].count - s.count;
    if (drop > worst.drop) worst = { i, drop };
  });
  return steps.map((s, i) => `
    <div class="meter-row">
      <div class="top"><span>${esc(STEP_LABELS[s.label] ?? s.label)}</span><span>${s.count}${i === worst.i ? ` <b style="color:var(--warn)">· biggest drop-off (−${worst.drop})</b>` : ''}</span></div>
      <div class="meter"><i style="width:${(s.count / max) * 100}%"></i></div>
    </div>`).join('');
}

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
    <div class="card"><h2>Checkout funnel</h2><p class="sub">How far customers get through the form</p>${stepFunnelHtml(f.steps)}</div>
    <div class="two">
      <div class="card"><h2>Devices</h2><p class="sub">What customers check out on</p>${meterList(v.devices, sum(v.devices))}</div>
      <div class="card"><h2>Referrers</h2><p class="sub">Where they came from</p>${meterList(v.referrers, sum(v.referrers))}</div>
    </div>
    <div class="card">
      <h2>Recent visits</h2><p class="sub">The most recent visits (up to 50); optionally filter by the start of the stored address — in the default truncated mode that's a /24, e.g. 203.0.113, not a full host IP like 203.0.113.7</p>
      <div class="row"><input data-role="ip-input" placeholder="Filter by IP prefix (optional)" style="max-width:260px"><button class="small" data-role="ip-search">Search</button></div>
      <div class="table-wrap" style="margin-top:12px"><table>
        <thead><tr><th>Time</th><th>IP</th><th>Country</th><th>City</th><th>Device</th><th>Referrer</th></tr></thead>
        <tbody id="ip-results"></tbody>
      </table></div>
    </div>
    <p class="muted" style="font-size:13px">Views are counted when a customer opens a checkout link (reloads within 10 minutes and bots are ignored). Visitors are identified by a first-party cookie, falling back to a salted hash of IP + browser. The IP itself is stored truncated by default (VISIT_IP_MODE) and resolved to a country/city when GeoIP databases are configured. Referrer is the page they came from, when the browser shares it.</p>`;

  const storeSelect = $('[data-role=store-filter]', root);
  if (storeSelect) bindStoreFilter(storeSelect, loadVisits);
  $('[data-role=range]', root).addEventListener('change', (e) => {
    state.rangeDays = Number(e.target.value);
    loadVisits();
  });
  $('[data-role=ip-search]', root).addEventListener('click', () => lookupByIp(root));
  $('[data-role=ip-input]', root).addEventListener('keydown', (e) => { if (e.key === 'Enter') lookupByIp(root); });
  lookupByIp(root); // shows the most recent visits straight away, with no filter needed
}

async function lookupByIp(root) {
  const ip = $('[data-role=ip-input]', root).value.trim();
  try {
    const rows = await api(`/visits/lookup?ip=${encodeURIComponent(ip)}&days=${state.rangeDays}`);
    $('#ip-results').innerHTML = rows.length
      ? rows.map((r) => `
          <tr><td>${esc(formatDate(r.at))}</td><td>${esc(r.ip)}</td><td>${esc(r.country || '—')}</td><td>${esc(r.city || '—')}</td><td>${esc(r.device)}</td><td>${esc(r.referrer || '—')}</td></tr>`).join('')
      : `<tr><td colspan="6" class="empty-inline">${ip ? 'No matching visits.' : 'No visits in this period.'}</td></tr>`;
  } catch (err) {
    flash(null, false, err.message);
  }
}
