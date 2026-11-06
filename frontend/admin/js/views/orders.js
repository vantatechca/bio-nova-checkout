// Pending / Paid / Failed tabs: order tables, "mark paid" flow and the order details drawer.
import { icon } from '/static/shared/icons.js';
import { api } from '../api.js';
import { refreshCounts } from '../counts.js';
import { state } from '../state.js';
import { $, $$, ORDER_STATUSES, PAYMENT_STATUSES, avatar, badge, esc, flash, formatDate, hydrateIcons, money } from '../util.js';

export const ORDER_TABS = ['pending', 'paid', 'failed'];

let orders = [];
const view = () => $('#view-orders');
const drawer = () => $('#drawer');

export function initOrdersView() {
  $('#status-filter').innerHTML += ORDER_STATUSES.map((s) => `<option>${s}</option>`).join('');
  let debounce;
  $('#search').addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(loadOrders, 250);
  });
  $('#status-filter').addEventListener('change', loadOrders);
  $('#refresh').addEventListener('click', loadOrders);

  $('#overlay').addEventListener('click', (e) => { if (e.target === $('#overlay')) closeDrawer(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
}

export async function loadOrders() {
  const tab = state.tab;
  const query = new URLSearchParams({ tab });
  if ($('#search').value.trim()) query.set('q', $('#search').value.trim());
  if ($('#status-filter').value) query.set('status', $('#status-filter').value);

  const [, result] = await Promise.all([refreshCounts(), api(`/orders?${query}`)]);
  orders = result.data;
  renderTable(tab, result.has_more);
}

function renderTable(tab, hasMore) {
  const pending = tab === 'pending';
  const paid = tab === 'paid';
  const note = $('#orders-intro');
  note.textContent = hasMore ? 'Showing the latest 500 orders — use search to find older ones.' : '';
  note.classList.toggle('hide', !hasMore);

  const headings = ['Order', 'Customer', 'Method', 'Total', paid ? 'Paid on' : 'Payment', 'Status', paid ? 'Reference' : '', ''];
  $('#orders-head').innerHTML = headings.map((h) => `<th>${h}</th>`).join('');
  $('#orders-body').innerHTML = orders.map((o) => `
    <tr class="clickable" data-id="${esc(o.id)}">
      <td><div class="order-no">#${o.number}<small>${esc(formatDate(o.created_at))}</small></div></td>
      <td><div class="who">${avatar(o.customer.name)}<div class="nm">${esc(o.customer.name)}<small>${esc(o.customer.email)}</small></div></div></td>
      <td><span class="method">${esc(o.payment_method.label)}</span></td>
      <td><span class="money">${money(o.total, o.currency)}</span></td>
      <td>${paid ? esc(formatDate(o.paid_at || o.created_at)) : badge(o.payment_status)}</td>
      <td>${badge(o.status)}</td>
      <td>${pending ? `<button class="success small" data-pay="${esc(o.id)}">${icon('check')} Mark paid</button>` : paid ? esc(o.payment_reference || '') : ''}</td>
      <td><span class="go">${icon('chevron')}</span></td>
    </tr>`).join('');
  $('#orders-empty').classList.toggle('hide', orders.length > 0);

  $$('#orders-body tr').forEach((row) => row.addEventListener('click', () => openOrder(row.dataset.id)));
  $$('[data-pay]', view()).forEach((button) =>
    button.addEventListener('click', (e) => {
      e.stopPropagation();
      quickMarkPaid(button.dataset.pay);
    }));
}

// ---------------------------------------------------------------- actions
function markPaid(id, reference, notify) {
  return api(`/orders/${id}`, { method: 'PATCH', body: { payment_status: 'paid', payment_reference: reference, notify } });
}

async function quickMarkPaid(id) {
  const order = orders.find((o) => o.id === id);
  const reference = prompt(
    `Mark order #${order.number} (${money(order.total, order.currency)}, ${order.payment_method.label}) as paid.\n\nPayment reference / confirmation # (optional):`,
    '',
  );
  if (reference === null) return;
  try {
    await markPaid(id, reference, true);
    flash(null, true, `Order #${order.number} marked as paid`);
    await loadOrders();
  } catch (err) {
    flash(null, false, err.message);
  }
}

// ---------------------------------------------------------------- drawer
function closeDrawer() { $('#overlay').classList.add('hide'); }

function openOrder(id) {
  const order = orders.find((o) => o.id === id);
  if (!order) return;
  drawer().innerHTML = drawerHtml(order);
  hydrateIcons(drawer());
  $('#overlay').classList.remove('hide');

  const d = drawer();
  const reopen = async () => {
    await loadOrders();
    if (orders.some((o) => o.id === id)) openOrder(id);
    else closeDrawer();
  };
  $('[data-role=close]', d).addEventListener('click', closeDrawer);

  const markPaidButton = $('[data-role=mark-paid]', d);
  if (markPaidButton) {
    markPaidButton.addEventListener('click', async () => {
      try {
        await markPaid(id, $('[data-role=payment-ref]', d).value, $('[data-role=receipt]', d).checked);
        flash(null, true, `Order #${order.number} marked as paid`);
        await reopen();
      } catch (err) {
        flash($('[data-role=paid-msg]', d), false, err.message);
      }
    });
  }

  $('[data-role=save]', d).addEventListener('click', async () => {
    try {
      await api(`/orders/${id}`, {
        method: 'PATCH',
        body: {
          status: $('[data-role=status]', d).value,
          payment_status: $('[data-role=payment-status]', d).value,
          tracking_number: $('[data-role=tracking]', d).value,
          notes: $('[data-role=notes]', d).value,
          notify: $('[data-role=notify]', d).checked,
        },
      });
      await reopen();
      flash($('[data-role=save-msg]', drawer()), true, 'Saved');
    } catch (err) {
      flash($('[data-role=save-msg]', d), false, err.message);
    }
  });
}

function drawerHtml(o) {
  const a = o.shipping_address;
  const awaitingPayment = o.payment_status !== 'paid' && o.status !== 'cancelled';
  const options = (values, current) => values.map((v) => `<option ${v === current ? 'selected' : ''}>${v}</option>`).join('');
  return `
    <div class="drawer-head">
      <div>
        <h2>Order #${o.number}</h2>
        <div class="meta">${badge(o.status)} ${badge(o.payment_status)} <span>${esc(formatDate(o.created_at))}</span>${o.external_ref ? `<span>· Ref ${esc(o.external_ref)}</span>` : ''}</div>
      </div>
      <button class="icon-only" data-role="close" aria-label="Close"><span data-icon="x"></span></button>
    </div>

    <div class="drawer-body">
      ${awaitingPayment ? `
      <div class="callout"><span class="ci" data-icon="clock"></span><div class="grow">
        <b>Awaiting payment — ${esc(o.payment_method.label)}</b>
        <p style="margin:4px 0 14px">Expecting ${money(o.total, o.currency)}. Once the transfer lands, record it here.</p>
        <label>Payment reference <span class="muted">(e.g. Zelle / Interac confirmation #)</span><input data-role="payment-ref" value="${esc(o.payment_reference)}"></label>
        <label class="inline"><input type="checkbox" class="switch" data-role="receipt" checked> Email the customer a payment receipt</label>
        <div class="row" style="margin-top:8px"><button class="success" data-role="mark-paid">Mark as paid</button><span class="msg" data-role="paid-msg"></span></div>
      </div></div>` : ''}

      <div class="two" style="gap:16px">
        <div class="block"><h3>Customer</h3><div class="who">${avatar(o.customer.name)}<div class="nm"><b>${esc(o.customer.name)}</b><small>${esc(o.customer.email)}</small>${o.customer.phone ? `<small>${esc(o.customer.phone)}</small>` : ''}</div></div></div>
        <div class="block"><h3>Ship to</h3><div class="address">${esc(a.line1)}${a.line2 ? `<br>${esc(a.line2)}` : ''}<br>${esc(a.city)}${a.state ? `, ${esc(a.state)}` : ''} ${esc(a.postal_code)}<br>${esc(a.country)}</div></div>
      </div>

      <div class="block"><h3>Items</h3>
        ${o.items.map((i) => `<div class="line"><span>${esc(i.name)}${i.sku ? ` <small>(${esc(i.sku)})</small>` : ''} <small>× ${i.quantity}</small></span><span class="num">${money(i.unit_amount * i.quantity, o.currency)}</span></div>`).join('')}
        <div class="line"><span class="muted">Shipping</span><span class="num">${money(o.shipping, o.currency)}</span></div>
        <div class="line"><span class="muted">Tax</span><span class="num">${money(o.tax, o.currency)}</span></div>
        <div class="line sum"><span>Total</span><span class="num">${money(o.total, o.currency)}</span></div>
        <p class="muted" style="margin-top:10px;font-size:13px">Payment: ${esc(o.payment_method.label)}${o.paid_at ? ` · paid ${esc(formatDate(o.paid_at))}` : ''}${o.payment_reference ? ` · ref ${esc(o.payment_reference)}` : ''}</p>
      </div>

      <div class="block"><h3>Manage</h3>
        <div class="grid2">
          <label>Order status<select data-role="status">${options(ORDER_STATUSES, o.status)}</select></label>
          <label>Payment status<select data-role="payment-status">${options(PAYMENT_STATUSES, o.payment_status)}</select></label>
        </div>
        <label>Tracking number<input data-role="tracking" value="${esc(o.tracking_number)}" placeholder="Optional"></label>
        <label>Internal notes<textarea data-role="notes" placeholder="Only visible to you">${esc(o.notes)}</textarea></label>
        <label class="inline"><input type="checkbox" class="switch" data-role="notify" checked> Email the customer about status changes</label>
        <div class="row" style="margin-top:14px"><button class="primary" data-role="save">Save changes</button><span class="msg" data-role="save-msg"></span></div>
      </div>

      <div class="block"><h3>History</h3>
        <ol class="timeline">${o.history.slice().reverse().map((h) => `<li><b>${esc(h.text)}</b><small>${esc(formatDate(h.at))}</small></li>`).join('')}</ol>
      </div>
    </div>`;
}
