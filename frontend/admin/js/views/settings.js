import { icon } from '/static/shared/icons.js';
import { api } from '../api.js';
import { refreshCounts } from '../counts.js';
import { $, $$, badge, esc, flash, formatDate } from '../util.js';

const MASK = '•'.repeat(24);

export async function loadSettings() {
  const cfg = await api('/settings');
  refreshCounts();
  const root = $('#view-settings');
  const paymentMethods = cfg.paymentMethods.map((m) => ({ ...m }));
  const navLinks = (cfg.navLinks ?? []).map((l) => ({ ...l }));
  const base = cfg.publicUrl.replace(/\/$/, '');

  root.innerHTML = `
    <div class="card"><div class="card-head"><div><h2>Connect your store</h2><p class="sub" style="margin:0">API key for server-to-server calls. Not for browser code.</p></div>
      <button class="primary" data-role="test-checkout">${icon('package')} Create test checkout</button></div>
      <label>API key</label>
      <div class="secret"><div class="mono" data-role="api-key">${MASK}</div><button data-role="show-key">Show</button><button class="danger" data-role="rotate-key">Rotate</button></div>
      <span class="msg" data-role="test-msg"></span>
      <h3>Create a checkout session</h3>
      <pre class="mono">curl -X POST ${esc(base)}/api/v1/checkout/sessions \\
  -H "Authorization: Bearer YOUR_API_KEY" -H "Content-Type: application/json" \\
  -d '{"items":[{"name":"Shirt","unit_amount":2500,"quantity":2}],"success_url":"https://yourstore.com/thanks","cancel_url":"https://yourstore.com/cart","external_ref":"cart_123"}'</pre>
      <p class="muted" style="font-size:13.5px;margin-top:10px">The response contains <code>checkout_url</code>, the page the customer is sent to. Amounts are in minor units (cents).</p>
    </div>

    <div class="card"><h2>Branding</h2><p class="sub">Make the customer checkout page match your storefront.</p>
      <div class="grid2">
        <label>Logo image URL <span class="muted">(https://… .png / .svg)</span><input data-field="logoUrl" placeholder="https://yourstore.com/logo.png" value="${esc(cfg.logoUrl)}"></label>
        <label>Store website <span class="muted">(where the logo links to)</span><input data-field="storeUrl" placeholder="https://yourstore.com" value="${esc(cfg.storeUrl)}"></label>
      </div>
      <label>Checkout notice <span class="muted">(optional — shown in a highlighted box, e.g. a policy or compliance notice)</span><textarea data-field="notice" maxlength="500" placeholder="Shown at the top of the checkout form and on the confirmation page">${esc(cfg.notice)}</textarea></label>
      <h3>Header menu links</h3>
      <p class="muted" style="font-size:13.5px;margin:0 0 12px">Up to 8 links shown in the checkout header, like your storefront's menu (HOME, SHOP, FAQ…).</p>
      <div data-role="nav-links"></div>
      <div class="row" style="margin-top:6px"><button data-role="add-link">${icon('plus')} Add link</button><button class="primary" data-role="save-branding">Save branding</button></div>
    </div>

    <div class="card"><h2>Shopify</h2><p class="sub">Send shoppers here when they click <b>Checkout</b> on your Shopify store. Orders are managed in this admin.</p>
      <div class="grid2">
        <label>Shop domain <span class="muted">(your-shop.myshopify.com)</span><input data-field="shopifyDomain" placeholder="your-shop.myshopify.com" value="${esc(cfg.shopifyDomain)}"></label>
        <label>Storefront API access token <span class="muted">(read-only product data)</span><input data-field="shopifyStorefrontToken" autocomplete="off" placeholder="shpat_… / token from your custom app" value="${esc(cfg.shopifyStorefrontToken)}"></label>
      </div>
      <div class="row"><button class="primary" data-role="test-shopify">Save &amp; test connection</button><span class="msg" data-role="shopify-msg"></span></div>
      <ol class="steps">
        <li><b>Get a token.</b> Shopify admin → <i>Settings → Apps and sales channels → Develop apps → Create an app</i>. Under <i>Configuration → Storefront API</i> tick <code>unauthenticated_read_product_listings</code>, install the app, and copy the <b>Storefront API access token</b>.</li>
        <li><b>Fill in the fields above</b> and your <b>Store website</b> under Branding, then press <i>Save &amp; test connection</i>.</li>
        <li><b>Add this line to your theme</b> — <i>Online Store → Themes → Edit code → layout/theme.liquid</i>, just before <code>&lt;/body&gt;</code>:
          <div class="secret"><div class="mono" data-role="snippet">&lt;script src="${esc(base)}/static/shopify/checkout-redirect.js" defer&gt;&lt;/script&gt;</div><button data-role="copy-snippet">Copy</button></div></li>
        <li><b>Turn off dynamic checkout buttons</b> (Shop Pay, Apple Pay) on product pages if your theme shows them — they skip this checkout. The script hides the usual ones automatically.</li>
      </ol>
      <p class="muted" style="font-size:13px">This service must be reachable at a public <b>https</b> address for shoppers (not <code>localhost</code>): set <code>PUBLIC_URL</code>. Shopify's own checkout stays reachable at <code>/checkout</code> for anyone who types it directly.</p>
    </div>

    <div class="card"><h2>Card payments</h2><p class="sub">Card payments are processed by the client's own processor through the client's API. Card numbers never reach this server.</p>
      <div class="grid2">
        <label>Card provider
          <select data-field="cardProvider">
            <option value="" ${cfg.cardProvider ? '' : 'selected'}>Not set up</option>
            <option value="embed" ${cfg.cardProvider === 'embed' ? 'selected' : ''}>Client-hosted card form (embedded)</option>
            <option value="redirect" ${cfg.cardProvider === 'redirect' ? 'selected' : ''}>Redirect to the client's payment page</option>
            <option value="mock" ${cfg.cardProvider === 'mock' ? 'selected' : ''}>Test provider (testing only)</option>
          </select></label>
        <label>Processor publishable key <span class="muted">(built-in providers only)</span><input data-field="cardPublicKey" autocomplete="off" placeholder="pk_live_…" value="${esc(cfg.cardPublicKey)}"></label>
      </div>
      <label>Client's card form URL <span class="muted">(https, embedded form only)</span><input data-field="cardFormUrl" placeholder="https://client-store.com/card-form" value="${esc(cfg.cardFormUrl)}"></label>
      <label>Client's API endpoint URL <span class="muted">(https)</span><input data-field="clientApiUrl" placeholder="https://client-store.com/api/checkout/charge" value="${esc(cfg.clientApiUrl)}"></label>
      <label>Signing secret <span class="muted">(signs every request sent to the client's API)</span></label>
      <div class="secret"><div class="mono" data-role="client-secret">${MASK}</div><button data-role="show-client-secret">Show</button><button class="danger" data-role="rotate-client-secret">Rotate</button></div>
      <div class="row" style="margin-top:14px"><button class="primary" data-role="test-card">Save &amp; test client API</button><button data-role="add-card-method">${icon('plus')} Add "Credit card" payment method</button><span class="msg" data-role="card-msg"></span></div>
      <p class="muted" style="font-size:13px;margin-top:12px">The card option appears at checkout once a provider and the client's API endpoint URL are set and a payment method of type <b>Card</b> exists below. Redirect payments stay Pending until the client's server marks them paid.</p>
    </div>

    <div class="card"><h2>Store &amp; checkout</h2><p class="sub">Defaults applied to every checkout.</p>
      <div class="grid2">
        <label>Store name<input data-field="storeName" value="${esc(cfg.storeName)}"></label>
        <label>Default currency<input data-field="currency" maxlength="3" value="${esc(cfg.currency)}"></label>
        <label>Default flat shipping <span class="muted">(minor units, e.g. 500 = 5.00)</span><input data-field="shippingFlat" type="number" min="0" step="1" value="${cfg.shippingFlat}"></label>
        <label>Default tax rate (%)<input data-field="taxRatePercent" type="number" min="0" max="100" step="0.01" value="${cfg.taxRatePercent}"></label>
      </div>
      <label>Allowed redirect domains <span class="muted">(comma separated, blank = any — recommended: your store's domain)</span><input data-field="allowedDomains" placeholder="yourstore.com" value="${esc(cfg.allowedDomains)}"></label>

      <h3>Payment methods</h3>
      <p class="muted" style="font-size:13.5px;margin:0 0 12px">Offline methods (Zelle, bank) leave the order in <b>Pending</b> until you mark it paid. In instructions, <code>{order}</code>, <code>{total}</code> and <code>{store}</code> are filled in automatically — set your real Zelle address here.</p>
      <div data-role="methods"></div>
      <button data-role="add-method">${icon('plus')} Add method</button>
      <div class="row" style="margin-top:20px"><button class="primary" data-role="save">Save settings</button><span class="msg" data-role="save-msg"></span></div>
    </div>

    <div class="card"><h2>Webhooks</h2><p class="sub">Get notified when orders are created, paid or updated.</p>
      <label>Webhook URL <span class="muted">(receives <code>order.created</code>, <code>order.paid</code>, <code>order.updated</code>)</span><input data-field="webhookUrl" placeholder="https://yourstore.com/webhooks/checkout" value="${esc(cfg.webhookUrl)}"></label>
      <label>Signing secret <span class="muted">(HMAC-SHA256 of the raw body, header <code>X-Checkout-Signature</code>)</span></label>
      <div class="secret"><div class="mono" data-role="webhook-secret">${MASK}</div><button data-role="show-secret">Show</button><button class="danger" data-role="rotate-secret">Rotate</button></div>
      <h3>Recent deliveries</h3>
      ${deliveriesHtml(cfg.webhookLog)}
    </div>`;

  const field = (name) => $(`[data-field=${name}]`, root);

  // ---- secrets: masked until revealed
  const secretReveal = (button, box, getValue) => {
    button.addEventListener('click', () => {
      const reveal = box.dataset.shown !== '1';
      box.textContent = reveal ? getValue() : MASK;
      box.dataset.shown = reveal ? '1' : '';
      button.textContent = reveal ? 'Hide' : 'Show';
    });
  };
  const keyBox = $('[data-role=api-key]', root), secretBox = $('[data-role=webhook-secret]', root);
  secretReveal($('[data-role=show-key]', root), keyBox, () => cfg.apiKey);
  secretReveal($('[data-role=show-secret]', root), secretBox, () => cfg.webhookSecret);

  const rotate = (button, confirmText, path, prop, box, toggle) => {
    button.addEventListener('click', async () => {
      if (!confirm(confirmText)) return;
      cfg[prop] = (await api(path, { method: 'POST' }))[prop];
      box.textContent = cfg[prop];
      box.dataset.shown = '1';
      $(toggle, root).textContent = 'Hide';
      flash(null, true, 'Rotated — copy the new value now');
    });
  };
  rotate($('[data-role=rotate-key]', root), 'Rotate the API key? Your store will stop working until you update it.', '/settings/rotate-key', 'apiKey', keyBox, '[data-role=show-key]');
  rotate($('[data-role=rotate-secret]', root), 'Rotate the webhook secret? Update your receiver afterward.', '/settings/rotate-webhook-secret', 'webhookSecret', secretBox, '[data-role=show-secret]');

  // ---- test checkout
  $('[data-role=test-checkout]', root).addEventListener('click', async () => {
    try {
      const session = await api('/test-session', { method: 'POST' });
      window.open(session.checkout_url, '_blank');
    } catch (err) {
      flash($('[data-role=test-msg]', root), false, err.message);
    }
  });

  // ---- header menu links editor
  const linksBox = $('[data-role=nav-links]', root);
  const drawLinks = () => {
    linksBox.innerHTML = navLinks.map((l, i) => `
      <div class="nav-link-row">
        <input data-li="${i}" data-lk="label" value="${esc(l.label)}" placeholder="Label (e.g. SHOP)" aria-label="Label">
        <input data-li="${i}" data-lk="url" value="${esc(l.url)}" placeholder="https://yourstore.com/shop" aria-label="URL">
        <button class="danger icon-only" data-remove-link="${i}" title="Remove" aria-label="Remove">${icon('x')}</button>
      </div>`).join('');
    $$('[data-lk]', linksBox).forEach((input) =>
      input.addEventListener('input', () => { navLinks[input.dataset.li][input.dataset.lk] = input.value; }));
    $$('[data-remove-link]', linksBox).forEach((button) =>
      button.addEventListener('click', () => { navLinks.splice(button.dataset.removeLink, 1); drawLinks(); }));
  };
  drawLinks();
  $('[data-role=add-link]', root).addEventListener('click', () => {
    if (navLinks.length >= 8) return flash(null, false, 'You can add up to 8 links');
    navLinks.push({ label: '', url: '' });
    drawLinks();
  });
  // Branding shares the page-wide "Save settings" request.
  $('[data-role=save-branding]', root).addEventListener('click', () => $('[data-role=save]', root).click());

  // ---- payment methods editor
  const methodsBox = $('[data-role=methods]', root);
  const drawMethods = () => {
    methodsBox.innerHTML = paymentMethods.map((m, i) => `
      <div class="payment-method">
        <input type="checkbox" class="switch" data-i="${i}" data-k="enabled" ${m.enabled ? 'checked' : ''} title="Enabled" aria-label="Enabled">
        <input data-i="${i}" data-k="label" value="${esc(m.label)}" placeholder="Label">
        <input data-i="${i}" data-k="instructions" value="${esc(m.instructions)}" placeholder="Instructions shown to the customer">
        <select data-i="${i}" data-k="type" aria-label="Type">
          <option value="offline" ${m.type === 'offline' ? 'selected' : ''}>Offline (manual)</option>
          <option value="card" ${m.type === 'card' ? 'selected' : ''}>Card (client's processor)</option>
          <option value="test" ${m.type === 'test' ? 'selected' : ''}>Test (auto-paid)</option>
        </select>
        <button class="danger icon-only" data-remove="${i}" title="Remove" aria-label="Remove">${icon('x')}</button>
      </div>`).join('');
    $$('[data-k]', methodsBox).forEach((input) => {
      const update = () => { paymentMethods[input.dataset.i][input.dataset.k] = input.type === 'checkbox' ? input.checked : input.value; };
      input.addEventListener('input', update);
      input.addEventListener('change', update);
    });
    $$('[data-remove]', methodsBox).forEach((button) =>
      button.addEventListener('click', () => { paymentMethods.splice(button.dataset.remove, 1); drawMethods(); }));
  };
  drawMethods();
  $('[data-role=add-method]', root).addEventListener('click', () => {
    paymentMethods.push({ id: '', label: 'New method', type: 'offline', instructions: '', enabled: true });
    drawMethods();
  });

  // ---- save (one request for every field on the page)
  const persist = async () => {
    await api('/settings', {
      method: 'PUT',
      body: {
        storeName: field('storeName').value,
        currency: field('currency').value,
        shippingFlat: Math.round(Number(field('shippingFlat').value) || 0),
        taxRatePercent: Number(field('taxRatePercent').value) || 0,
        allowedDomains: field('allowedDomains').value,
        logoUrl: field('logoUrl').value,
        storeUrl: field('storeUrl').value,
        notice: field('notice').value,
        navLinks: navLinks.filter((l) => l.label.trim() || l.url.trim()),
        shopifyDomain: field('shopifyDomain').value,
        shopifyStorefrontToken: field('shopifyStorefrontToken').value,
        cardProvider: field('cardProvider').value,
        cardPublicKey: field('cardPublicKey').value,
        cardFormUrl: field('cardFormUrl').value,
        clientApiUrl: field('clientApiUrl').value,
        webhookUrl: field('webhookUrl').value,
        paymentMethods,
      },
    });
    const name = field('storeName').value || 'Orders';
    $('#brand').textContent = name;
    $('#logo').textContent = name.trim()[0]?.toUpperCase() || 'C';
  };
  $('[data-role=save]', root).addEventListener('click', async () => {
    const message = $('[data-role=save-msg]', root);
    try { await persist(); flash(message, true, 'Saved'); }
    catch (err) { flash(message, false, err.message); }
  });

  // ---- card payments: client API secret, connection test, and a shortcut to add the "Card" payment method
  const clientSecretBox = $('[data-role=client-secret]', root);
  secretReveal($('[data-role=show-client-secret]', root), clientSecretBox, () => cfg.clientApiSecret);
  rotate($('[data-role=rotate-client-secret]', root), 'Rotate the signing secret? The client must update it, or card payments will fail.', '/card/rotate-secret', 'clientApiSecret', clientSecretBox, '[data-role=show-client-secret]');
  $('[data-role=test-card]', root).addEventListener('click', async () => {
    const message = $('[data-role=card-msg]', root);
    message.className = 'msg';
    message.textContent = 'Checking…';
    try {
      await persist();
      await api('/card/test', { method: 'POST' });
      flash(message, true, "The client's API answered and accepted our signature");
    } catch (err) {
      flash(message, false, err.message);
    }
  });
  $('[data-role=add-card-method]', root).addEventListener('click', () => {
    if (paymentMethods.some((m) => m.type === 'card')) return flash(null, false, 'A card payment method already exists');
    paymentMethods.unshift({ id: 'card', label: 'Credit card', type: 'card', instructions: '', enabled: true });
    drawMethods();
    flash(null, true, 'Added — press Save settings');
  });

  // ---- Shopify connector: save, then ask Shopify for the shop name to prove the token works
  $('[data-role=test-shopify]', root).addEventListener('click', async () => {
    const message = $('[data-role=shopify-msg]', root);
    message.className = 'msg';
    message.textContent = 'Checking…';
    try {
      await persist();
      const { shop_name: shopName } = await api('/shopify/test', { method: 'POST' });
      flash(message, true, `Connected to ${shopName}`);
    } catch (err) {
      flash(message, false, err.message);
    }
  });
  $('[data-role=copy-snippet]', root).addEventListener('click', async (e) => {
    try { await navigator.clipboard.writeText($('[data-role=snippet]', root).textContent); } catch { /* clipboard unavailable */ }
    e.currentTarget.textContent = 'Copied';
    setTimeout(() => { e.currentTarget.textContent = 'Copy'; }, 1800);
  });
}

function deliveriesHtml(log) {
  if (!log.length) return '<p class="empty-inline">No deliveries yet.</p>';
  return log.slice(0, 10).map((d) => {
    const outcome = d.error
      ? `<span class="badge b-failed" title="${esc(d.error)}">Error</span>`
      : d.status ? `<span class="badge b-${d.status < 300 ? 'paid' : 'failed'}">${d.status}</span>` : badge('pending');
    return `<div class="line"><span>${esc(d.event)} <small>#${esc(d.order)} · ${esc(formatDate(d.at))}${d.attempts > 1 ? ` · ${d.attempts} attempts` : ''}</small></span><span>${outcome}</span></div>`;
  }).join('');
}
