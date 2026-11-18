// Ads Data and Sites tabs: cards filled by an automated feed (see docs/content-panels.md).
// The content is the same for every checkout, so nothing here depends on which one is selected.
import { icon } from '/static/shared/icons.js';
import { api } from '../api.js';
import { refreshCounts } from '../counts.js';
import { $, esc, formatDate } from '../util.js';

const safeUrl = (url) => (/^https?:\/\//i.test(url ?? '') ? url : '');
const link = (url, text) => (safeUrl(url)
  ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`
  : esc(text));

const GOOD = /^(up|live|active|ok|good|online|verified|paid|published)$/i;
const BAD = /^(down|offline|error|failed|inactive|suspended|blocked)$/i;
const WARN = /^(warn|warning|degraded|slow|pending|partial|review)$/i;
const statusBadge = (value) => {
  const tone = GOOD.test(value) ? 'b-completed' : BAD.test(value) ? 'b-failed' : WARN.test(value) ? 'b-pending' : '';
  return `<span class="badge ${tone}">${esc(value)}</span>`;
};

const amount = (value, currency) => {
  try {
    return new Intl.NumberFormat(undefined, currency ? { style: 'currency', currency } : { maximumFractionDigits: 2 }).format(value);
  } catch {
    return String(value);
  }
};

// ---------------------------------------------------------------- the parts a section can show
const metrics = (list) => `<div class="pm-grid">${list.map((m) => {
  const trend = m.trend ? `<span class="pm-trend ${String(m.trend).trim().startsWith('-') ? 'down' : 'up'}">${esc(m.trend)}</span>` : '';
  return `<div class="pm"><small>${esc(m.label)}</small><b>${esc(m.value)}</b>${trend}${m.hint ? `<i>${esc(m.hint)}</i>` : ''}</div>`;
}).join('')}</div>`;

const entries = (list) => `<ul class="pe-list">${list.map((e) => {
  const image = safeUrl(e.image_url);
  const thumb = image ? `<img class="pe-thumb" src="${esc(image)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '';
  const where = [e.subtitle, e.city].filter(Boolean).map(esc).join(' · ');
  const rating = e.rating != null ? `<span class="pe-rating">${icon('star')} ${esc(e.rating)}</span>` : '';
  return `<li>${thumb}<div class="pe-main"><b>${link(e.url, e.title)}</b>${where ? `<small>${where}</small>` : ''}${e.note ? `<small>${esc(e.note)}</small>` : ''}</div>
    <div class="pe-side">${e.status ? statusBadge(e.status) : ''}${rating}${e.value != null ? `<span class="money">${esc(e.value)}</span>` : ''}${e.updated_at ? `<small>${esc(formatDate(e.updated_at))}</small>` : ''}</div></li>`;
}).join('')}</ul>`;

const siteRows = (list) => `<div class="table-wrap"><table>
  <thead><tr><th>Site</th><th>Status</th><th>Uptime</th><th>Response</th><th>Last checked</th></tr></thead>
  <tbody>${list.map((s) => `<tr>
    <td><div class="nm">${link(s.url, s.name)}${s.url ? `<small>${esc(s.url)}</small>` : ''}</div></td>
    <td>${s.status ? statusBadge(s.status) : '—'}</td>
    <td>${s.uptime_pct != null ? `${esc(s.uptime_pct)}%` : '—'}</td>
    <td>${s.response_ms != null ? `${esc(s.response_ms)} ms` : '—'}</td>
    <td>${esc(formatDate(s.last_checked_at))}</td></tr>`).join('')}</tbody></table></div>`;

const cardRows = (list) => `<ul class="pe-list">${list.map((c) => {
  const money = c.spend != null
    ? `<span class="money">${esc(amount(c.spend, c.currency))}</span>${c.limit != null ? `<small>of ${esc(amount(c.limit, c.currency))}</small>` : ''}`
    : '';
  return `<li><span class="pe-thumb pe-icon">${icon('card')}</span>
    <div class="pe-main"><b>${esc(c.label)}</b><small>${c.brand ? `${esc(c.brand)} ` : ''}•••• ${esc(c.last4)}</small>${c.note ? `<small>${esc(c.note)}</small>` : ''}</div>
    <div class="pe-side">${c.status ? statusBadge(c.status) : ''}${money}</div></li>`;
}).join('')}</ul>`;

const dataTable = (t) => `<div class="table-wrap"><table>
  <thead><tr>${t.columns.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead>
  <tbody>${t.rows.map((row) => `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;

function content(c) {
  const parts = [];
  if (c.headline) parts.push(`<p class="pc-headline">${esc(c.headline)}</p>`);
  if (c.summary) parts.push(`<p class="pc-summary">${esc(c.summary)}</p>`);
  if (c.metrics?.length) parts.push(metrics(c.metrics));
  if (c.cards?.length) parts.push(cardRows(c.cards));
  if (c.sites?.length) parts.push(siteRows(c.sites));
  if (c.entries?.length) parts.push(entries(c.entries));
  if (c.table) parts.push(dataTable(c.table));
  return parts.join('') || '<p class="empty-inline">Nothing to show yet.</p>';
}

// ---------------------------------------------------------------- cards and page
const TIERS = { included: 'Included', addon: 'Add-on' };

function head(s, extra = '') {
  const tier = s.tier ? `<span class="pc-tier ${esc(s.tier)}">${esc(TIERS[s.tier] ?? s.tier)}</span>` : '';
  return `<div class="pcard-head"><span class="chip-ico">${icon(s.icon)}</span>
    <div class="pcard-title"><h2>${esc(s.title)}</h2><p class="sub">${esc(s.subtitle)}</p></div>${tier}${extra}</div>`;
}

const liveCard = (s) => `<article class="card pcard live">
  ${head(s, s.has_pending ? '<span class="badge b-pending" title="Newer content is waiting to be published">Update waiting</span>' : '')}
  ${content(s.content)}
  ${s.updated_at ? `<p class="pc-foot">Updated ${esc(formatDate(s.updated_at))}</p>` : ''}</article>`;

const soonCard = (s) => `<article class="card pcard soon">${head(s)}
  <div class="pc-soon"><span class="badge b-pending">Coming soon</span></div></article>`;

/** One banner while nothing is published at all; as soon as one section is live, the cards take over. */
export async function loadPanel(slug) {
  const [, panel] = await Promise.all([refreshCounts(), api(`/panels/${slug}`)]);
  const root = $(`#view-${slug}`);
  const nothingLive = panel.sections.every((s) => s.status !== 'live');
  root.innerHTML = nothingLive
    ? `<div class="card"><div class="empty"><div class="empty-art">${icon('clock')}</div><b>Coming soon</b>
        <ul class="soon-list">${panel.sections.map((s) => `<li><span class="chip-ico">${icon(s.icon)}</span>
          <span>${esc(s.title)}</span>${s.tier ? `<span class="pc-tier ${esc(s.tier)}">${esc(TIERS[s.tier] ?? s.tier)}</span>` : ''}</li>`).join('')}</ul></div></div>`
    : `<div class="pgrid">${panel.sections.map((s) => (s.status === 'live' ? liveCard(s) : soonCard(s))).join('')}</div>`;
}
