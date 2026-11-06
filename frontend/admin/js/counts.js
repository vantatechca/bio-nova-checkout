// Order counters on the Pending / Paid / Failed tabs.
import { api } from './api.js';
import { $ } from './util.js';

export async function refreshCounts() {
  const stats = await api('/stats');
  for (const key of ['pending', 'paid', 'failed']) {
    $(`[data-count="${key}"]`).textContent = stats.counts[key];
  }
  $('[data-tab="pending"]').classList.toggle('hot', stats.counts.pending > 0);
  return stats;
}

