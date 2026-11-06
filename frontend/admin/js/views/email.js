import { icon } from '/static/shared/icons.js';
import { api } from '../api.js';
import { stat } from '../components.js';
import { refreshCounts } from '../counts.js';
import { $, $$, avatar, badge, esc, flash, formatDate } from '../util.js';

const NOTIFICATIONS = [
  ['confirmation', 'Order confirmation', 'Includes Zelle / Interac instructions when payment is owed'],
  ['paid', 'Payment received', 'Sent when you mark an order paid'],
  ['shipped', 'Order shipped', 'Includes the tracking number'],
  ['cancelled', 'Order cancelled', 'Lets the customer know right away'],
  ['admin', 'New-order alert to me', 'Needs the "notify me" address above'],
];

export async function loadEmail() {
  const [, data] = await Promise.all([refreshCounts(), api('/email')]);
  const root = $('#view-email');
  const { smtp, notify, adminEmail } = data.settings;

  root.innerHTML = `
    <div class="stats">
      ${stat('Sent (30d)', data.stats.sent, '', 'mail', 'ok')}
      ${stat('Failed (30d)', data.stats.failed, '', 'x-circle', 'danger')}
      ${stat('Skipped (30d)', data.stats.skipped, 'SMTP not set up', 'clock', 'warn')}
    </div>
    ${smtp.host ? '' : `<div class="callout warn"><span class="ci">${icon('mail')}</span><div><b>Email isn't set up yet.</b><p>Add your SMTP details below — until then, emails are logged as "skipped" and nothing is sent.</p></div></div>`}

    <div class="card"><h2>SMTP</h2><p class="sub">The mail server used to send customer emails.</p>
      <div class="grid2">
        <label>Host<input data-field="host" placeholder="smtp.gmail.com" value="${esc(smtp.host)}"></label>
        <label>Port<input data-field="port" type="number" value="${smtp.port}"></label>
        <label>Username<input data-field="user" autocomplete="off" value="${esc(smtp.user)}"></label>
        <label>Password ${smtp.passSet ? '<span class="muted">(saved — leave blank to keep)</span>' : ''}<input data-field="pass" type="password" autocomplete="new-password" placeholder="${smtp.passSet ? '••••••••' : ''}"></label>
        <label>From <span class="muted">(e.g. My Store &lt;orders@yourstore.com&gt;)</span><input data-field="from" value="${esc(smtp.from)}"></label>
        <label>Notify me of new orders at<input data-field="adminEmail" type="email" placeholder="you@yourstore.com" value="${esc(adminEmail)}"></label>
      </div>
      <label class="inline"><input type="checkbox" class="switch" data-field="secure" ${smtp.secure ? 'checked' : ''}> Use implicit TLS (port 465). Leave off for 587 / STARTTLS.</label>
      <p class="muted" style="font-size:13px;margin-top:8px">The password is stored unencrypted in your database's <code>settings</code> table — use an app password or a dedicated sending account, and restrict database access.</p>

      <h3>Send these emails</h3>
      ${NOTIFICATIONS.map(([key, title, hint]) => `<label class="inline"><input type="checkbox" class="switch" data-notify="${key}" ${notify[key] ? 'checked' : ''}><span class="grow"><b>${title}</b><br><span class="muted" style="font-size:13px;font-weight:400">${hint}</span></span></label>`).join('')}
      <div class="row" style="margin-top:18px"><button class="primary" data-role="save">Save email settings</button><span class="msg" data-role="save-msg"></span></div>

      <h3>Send a test</h3>
      <div class="row"><input data-role="test-to" type="email" placeholder="send a test to…" style="max-width:300px;margin:0"><button data-role="send-test">${icon('mail')} Send test</button><span class="msg" data-role="test-msg"></span></div>
    </div>

    <div class="card flush">
      <div style="padding:20px 24px 4px"><h2>Recent emails</h2></div>
      <div class="table-wrap"><table>
        <thead><tr><th>When</th><th>To</th><th>Type</th><th>Order</th><th>Status</th><th></th></tr></thead>
        <tbody>${data.log.map(logRow).join('') || '<tr><td colspan="6" class="empty-inline">No emails yet.</td></tr>'}</tbody>
      </table></div>
    </div>`;

  const field = (name) => $(`[data-field=${name}]`, root);
  const save = async () => {
    const notifyFlags = Object.fromEntries($$('[data-notify]', root).map((box) => [box.dataset.notify, box.checked]));
    await api('/email', {
      method: 'PUT',
      body: {
        adminEmail: field('adminEmail').value,
        notify: notifyFlags,
        smtp: {
          host: field('host').value,
          port: Number(field('port').value),
          secure: field('secure').checked,
          user: field('user').value,
          pass: field('pass').value,
          from: field('from').value,
        },
      },
    });
  };

  $('[data-role=save]', root).addEventListener('click', async () => {
    try { await save(); flash($('[data-role=save-msg]', root), true, 'Saved'); }
    catch (err) { flash($('[data-role=save-msg]', root), false, err.message); }
  });

  $('[data-role=send-test]', root).addEventListener('click', async () => {
    const message = $('[data-role=test-msg]', root);
    message.className = 'msg';
    message.textContent = 'Sending…';
    try {
      await save();
      await api('/email/test', { method: 'POST', body: { to: $('[data-role=test-to]', root).value } });
      flash(message, true, 'Sent — check the inbox');
    } catch (err) {
      flash(message, false, err.message);
    }
  });

  $$('[data-retry]', root).forEach((button) =>
    button.addEventListener('click', async () => {
      button.disabled = true;
      try { await api(`/email/${button.dataset.retry}/retry`, { method: 'POST' }); }
      finally { loadEmail(); }
    }));
}

function logRow(e) {
  return `<tr>
    <td>${esc(formatDate(e.at))}</td>
    <td><div class="who">${avatar(e.to)}<div class="nm">${esc(e.to)}</div></div></td>
    <td>${esc(e.type)}</td><td><span class="order-no">#${e.order}</span></td>
    <td>${badge(e.status)}${e.error ? `<small class="muted" style="display:block;margin-top:4px">${esc(e.error)}</small>` : ''}</td>
    <td>${e.status === 'sent' ? '' : `<button class="small" data-retry="${esc(e.id)}">Retry</button>`}</td>
  </tr>`;
}
