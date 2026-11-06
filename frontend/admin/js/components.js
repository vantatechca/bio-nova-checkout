// Reusable HTML fragments (all interpolated values are escaped).
import { icon } from '/static/shared/icons.js';
import { esc } from './util.js';
import { state } from './state.js';

/** KPI card. `tone` is one of ok | warn | danger | info (default: brand). */
export function stat(label, value, sub = '', iconName = 'receipt', tone = '') {
  return `<div class="stat ${tone ? `tone-${tone}` : ''}"><div class="chip-ico">${icon(iconName)}</div><small>${label}</small><b>${value}</b>${sub ? `<i>${sub}</i>` : ''}</div>`;
}

export function rangeSelect() {
  const options = [7, 30, 90]
    .map((d) => `<option value="${d}" ${d === state.rangeDays ? 'selected' : ''}>Last ${d} days</option>`)
    .join('');
  return `<div class="toolbar-range"><select data-role="range" aria-label="Date range">${options}</select></div>`;
}

/** Bar chart of `key` over `data` (each item has a `date`). `format` renders values for the tooltip. */
export function barChart(data, key, format) {
  const max = Math.max(...data.map((d) => d[key]), 1);
  const bars = data
    .map((d, i) => `<div style="height:${(d[key] / max) * 100}%;animation-delay:${Math.min(i * 12, 400)}ms" data-tip="${esc(d.date)} · ${esc(format(d[key]))}"></div>`)
    .join('');
  return `<div class="chart" role="img" aria-label="Daily ${key} chart">${bars}</div>
    <div class="axis"><span>${esc(data[0].date)}</span><span>peak ${esc(format(max))}</span><span>${esc(data[data.length - 1].date)}</span></div>`;
}

/** Labelled horizontal meters, e.g. devices or referrers. */
export function meterList(rows, total) {
  if (!rows.length) return '<p class="empty-inline">No data yet.</p>';
  return rows
    .map(
      (r) => `<div class="meter-row">
        <div class="top"><span>${esc(r.label)}</span><span>${r.count} · ${Math.round((r.count / total) * 100)}%</span></div>
        <div class="meter"><i style="width:${(r.count / total) * 100}%"></i></div></div>`,
    )
    .join('');
}
