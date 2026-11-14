// Customer-facing checkout page. Talks only to the public session API.
import { icon } from '/static/shared/icons.js';
import { loadProvider } from '/static/checkout/card/index.js';
import { countries, regionsFor } from '/static/checkout/regions.js';

const app = document.querySelector('#app');
const sessionId = new URLSearchParams(location.search).get('session');
let session = null;

// Current promotion: spending this much (in cents) unlocks free shipping. Change it here when the promotion changes.
const FREE_SHIPPING_FROM = 7000;

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ESCAPES[c]);

const money = (minorUnits) => {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: session.currency }).format(minorUnits / 100);
  } catch {
    return `${(minorUnits / 100).toFixed(2)} ${session.currency}`;
  }
};
const safeHttpUrl = (url) => {
  try { return /^https?:$/.test(new URL(url).protocol) ? url : null; } catch { return null; }
};
const initial = (text) => (String(text ?? '').trim()[0] || '•').toUpperCase();

// ---------------------------------------------------------------- header (matches the storefront)
function renderHeader() {
  const branding = session?.branding ?? { logo_url: '', store_url: '', nav_links: [], notice: '' };
  const name = session?.storeName ?? 'Checkout';
  const home = safeHttpUrl(branding.store_url) || safeHttpUrl(session?.cancel_url) || '#';
  const logo = safeHttpUrl(branding.logo_url)
    ? `<img src="${esc(branding.logo_url)}" alt="${esc(name)}" referrerpolicy="no-referrer">`
    : `<span class="wordmark">${esc(name)}</span>`;
  const links = branding.nav_links
    .filter((l) => safeHttpUrl(l.url))
    .map((l) => `<a href="${esc(l.url)}">${esc(l.label)}</a>`)
    .join('');

  document.querySelector('#site-header').innerHTML = `
    <div class="header-inner">
      <a class="brand" href="${esc(home)}" aria-label="${esc(name)} home">${logo}</a>
      <nav class="main-nav" aria-label="Store">${links}</nav>
      <div class="header-tools">
        <span class="secure-pill">${icon('lock')}<span class="txt">Secure checkout</span></span>
      </div>
    </div>`;
}

// ---------------------------------------------------------------- shell pieces
function setStepper(current) {
  const steps = [['Details & payment', 1], ['Confirmation', 2]];
  const stepper = document.querySelector('#stepper');
  stepper.hidden = false;
  stepper.innerHTML = steps.map(([label, n], i) => {
    const state = n < current ? 'done' : n === current ? 'current' : '';
    const dot = n < current ? icon('check') : n;
    return `${i ? `<span class="step-line ${n <= current ? 'done' : ''}"></span>` : ''}
      <div class="step ${state}" ${state === 'current' ? 'aria-current="step"' : ''}><span class="dot">${dot}</span><span class="label">${label}</span></div>`;
  }).join('');
}

function showMessage({ iconName = 'clock', title, text }) {
  renderHeader();
  document.querySelector('#stepper').hidden = true;
  app.className = 'layout single';
  app.innerHTML = `<div class="state-card"><div class="state-icon">${icon(iconName)}</div><h2>${esc(title)}</h2><p>${esc(text)}</p></div>`;
}

const noticeHtml = () => (session.branding.notice ? `<div class="notice">${esc(session.branding.notice)}</div>` : '');

// ---------------------------------------------------------------- boot
async function init() {
  if (!sessionId) {
    return showMessage({ iconName: 'link', title: 'No checkout session', text: 'This link is missing its session. Please return to the store and try again.' });
  }
  const response = await fetch(`/api/public/sessions/${encodeURIComponent(sessionId)}?ref=${encodeURIComponent(document.referrer || '')}`);
  if (!response.ok) {
    return showMessage({ iconName: 'x-circle', title: 'Checkout not found', text: 'This checkout link is invalid. Please return to the store.' });
  }
  session = await response.json();
  document.title = `Checkout · ${session.storeName}`;
  renderHeader();

  if (session.status === 'expired') {
    return showMessage({ title: 'This checkout has expired', text: 'Please return to the store and start again.' });
  }
  if (session.status === 'complete') {
    showConfirmation(session.order_number, session.success_url, session.payment_status === 'paid' ? '' : session.payment_instructions, session.payment_url);
    if (session.payment_status === 'pending' && session.card?.provider === 'redirect') pollUntilPaid();
    return;
  }
  renderForm();
}

/** After coming back from the client's payment page the order may take a moment to be marked paid: check for ~2 minutes. */
function pollUntilPaid(attempts = 30) {
  if (attempts <= 0) return;
  setTimeout(async () => {
    try {
      const response = await fetch(`/api/public/sessions/${encodeURIComponent(sessionId)}`);
      const latest = response.ok ? await response.json() : null;
      if (latest?.payment_status === 'paid') {
        session = latest;
        return showConfirmation(latest.order_number, latest.success_url, '');
      }
    } catch { /* try again */ }
    pollUntilPaid(attempts - 1);
  }, 4000);
}

// ---------------------------------------------------------------- order summary
function summaryHtml() {
  const count = session.items.reduce((n, i) => n + i.quantity, 0);
  const items = session.items.map((item) => `
    <div class="item">
      <div class="thumb">${item.image ? `<img src="${esc(item.image)}" alt="" referrerpolicy="no-referrer">` : esc(initial(item.name))}<span class="qty">${item.quantity}</span></div>
      <div class="item-name">${esc(item.name)}${item.description ? `<small>${esc(item.description)}</small>` : ''}</div>
      <div class="item-price num">${money(item.unit_amount * item.quantity)}</div>
    </div>`).join('');
  return `
    <aside class="summary" id="summary">
      <div class="summary-head"><h2>Order summary</h2><span>${count} ${count === 1 ? 'item' : 'items'}</span></div>
      <div class="items">${items}</div>
      <div class="totals">
        <div class="line"><span>Subtotal</span><span class="num">${money(session.subtotal)}</span></div>
        <div class="line"><span>Shipping</span><span class="num">${session.shipping ? money(session.shipping) : '<span class="free">Free</span>'}</span></div>
        ${session.tax ? `<div class="line"><span>Tax</span><span class="num">${money(session.tax)}</span></div>` : ''}
        <div class="line total"><span>Total</span><span class="num"><small>${esc(session.currency)}</small>${money(session.total)}</span></div>
      </div>
      ${promoHtml()}
    </aside>`;
}

// ---------------------------------------------------------------- payment options
const PAYMENT_ICONS = { bank: 'bank', test: 'flask', card: 'card' };
function paymentMethodsHtml() {
  if (!session.paymentMethods.length) return '<p class="error">No payment methods are available right now.</p>';
  const [only] = session.paymentMethods;
  if (session.paymentMethods.length === 1 && only.type === 'card') {
    // Card is the only way to pay: nothing to choose, so show a heading with the card form directly beneath it.
    return `
      <div class="pay-single"><span class="pay-icon">${icon('card')}</span>
        <div><span class="pay-title">${esc(only.label)}</span>${only.instructions ? `<small>${esc(only.instructions)}</small>` : ''}</div></div>
      <input type="radio" name="payment" value="${esc(only.id)}" checked hidden>
      <div class="card-fields" data-card-fields></div>`;
  }
  return `<div class="pay-list" role="radiogroup" aria-label="Payment method">${session.paymentMethods.map((method, i) => `
    <label class="pay-card">
      <input type="radio" name="payment" value="${esc(method.id)}" ${i === 0 ? 'checked' : ''}>
      <span class="pay-icon">${icon(PAYMENT_ICONS[method.id] ?? (method.type === 'card' ? 'card' : 'transfer'))}</span>
      <span class="pay-body"><span class="pay-title">${esc(method.label)}</span>${method.instructions ? `<span class="pay-sub"><small>${esc(method.instructions)}</small></span>` : ''}</span>
      <span class="pay-check">${icon('check')}</span>
    </label>${method.type === 'card' ? '<div class="card-fields" data-card-fields hidden></div>' : ''}`).join('')}</div>`;
}

// ---------------------------------------------------------------- card fields (the processor's, never ours)
let cardHandle = null; // { tokenize(), destroy() } from the card provider once its fields are mounted

const selectedMethod = () => {
  const id = document.querySelector('input[name=payment]:checked')?.value;
  return session.paymentMethods.find((m) => m.id === id);
};

/** Shows the card fields when "card" is the selected method, loading the provider the first time. */
async function syncCardFields() {
  const box = document.querySelector('[data-card-fields]');
  if (!box) return;
  const isCard = selectedMethod()?.type === 'card';
  box.hidden = !isCard;
  if (!isCard || cardHandle) return;
  if (session.card.provider === 'redirect') { // no card fields here: the customer pays on the client's payment page
    box.innerHTML = '<p class="redirect-note">After you press Pay, you\'ll be taken to our secure payment partner to enter your card details.</p>';
    cardHandle = { tokenize: async () => '', destroy() {} };
    return;
  }
  box.innerHTML = '<div class="spinner" aria-label="Loading card form"></div>';
  try {
    const provider = await loadProvider(session.card.provider);
    if (!provider) throw new Error(`No card provider "${session.card.provider}"`);
    box.innerHTML = '';
    cardHandle = await provider.mount(box, { publicKey: session.card.public_key, formUrl: session.card.form_url });
  } catch {
    const another = session.paymentMethods.length > 1 ? ' Please choose another payment method.' : ' Please try again in a moment.';
    box.innerHTML = `<p class="error">Card payments are unavailable right now.${another}</p>`;
  }
}

/** "Pay · $55.00" for cards, "Place order · $55.00" for methods that are paid afterwards. */
const ctaLabel = (method = selectedMethod()) => `${method?.type === 'card' ? 'Pay' : 'Place order'} · ${money(session.total)}`;

function wirePaymentMethods() {
  cardHandle = null;
  document.querySelectorAll('input[name=payment]').forEach((radio) =>
    radio.addEventListener('change', () => {
      syncCardFields();
      const button = document.querySelector('#submit');
      if (button && !button.disabled) button.textContent = ctaLabel();
    }));
  syncCardFields();
}

// ---------------------------------------------------------------- trust
const trustHtml = (cls = 'trust-side') => `
  <ul class="trust ${cls}" aria-label="Checkout security">
    <li>${icon('lock')}<div><b>Safe &amp; secure payment</b><span>Your personal and payment details are kept private and protected.</span></div></li>
    <li>${icon('shield')}<div><b>Your card details stay private</b><span>Card numbers go straight to our payment partner and are never stored here.</span></div></li>
    <li>${icon('package')}<div><b>Your order number right away</b><span>You'll see your order number as soon as you place your order. Questions? Use the chat on our store.</span></div></li>
  </ul>`;

// ---------------------------------------------------------------- form
function renderForm() {
  const customer = session.customer || {};
  const cancelUrl = session.cancel_url && safeHttpUrl(session.cancel_url);
  setStepper(1);
  app.className = 'layout';
  app.innerHTML = `
    <form class="flow" id="checkout-form" novalidate>
      ${noticeHtml()}
      <section class="panel">
        <div class="panel-head"><h2><span class="num-badge">1</span>Contact</h2><p>We'll send your receipt and updates here.</p></div>
        <fieldset>
          <label><span class="req">Full name</span><input name="name" autocomplete="name" autocapitalize="words" enterkeyhint="next" placeholder="Ada Lovelace" required value="${esc(customer.name)}"></label>
          <div class="row">
            <label><span class="req">Email</span><input name="email" type="email" inputmode="email" autocomplete="email" placeholder="you@example.com" required value="${esc(customer.email)}"></label>
            <label>Phone <span class="hint">(optional)</span><input name="phone" type="tel" autocomplete="tel" placeholder="+1 555 123 4567" value="${esc(customer.phone)}"></label>
          </div>
        </fieldset>
      </section>

      <section class="panel">
        <div class="panel-head"><h2><span class="num-badge">2</span>Shipping address</h2><p>Where should we send your order?</p></div>
        <fieldset>
          <label><span class="req">Address</span><input name="line1" autocomplete="address-line1" autocapitalize="words" enterkeyhint="next" placeholder="123 Main Street" required></label>
          <label>Apartment, suite, etc. <span class="hint">(optional)</span><input name="line2" autocomplete="address-line2"></label>
          <div class="row">
            <label><span class="req">City</span><input name="city" autocomplete="address-level2" autocapitalize="words" enterkeyhint="next" required></label>
            <label><span class="req">Country</span><select name="country" autocomplete="country-name" required>
              ${countries().length > 1 ? '<option value="">Select a country</option>' : ''}${countries().map((c) => `<option>${esc(c)}</option>`).join('')}
            </select></label>
          </div>
          <div class="row">
            <label data-role="state-field">State / Province<input name="state" autocomplete="address-level1"></label>
            <label><span class="req">Postal code</span><input name="postal_code" autocomplete="postal-code" inputmode="numeric" enterkeyhint="done" required></label>
          </div>
        </fieldset>
      </section>

      <section class="panel">
        <div class="panel-head"><h2><span class="num-badge">3</span>Payment</h2><p>${session.paymentMethods.length === 1 ? 'Enter your card details to pay.' : "Choose how you'd like to pay."}</p></div>
        <fieldset>${paymentMethodsHtml()}</fieldset>
        <div style="margin-top:22px">
          <p class="error" id="error" role="alert"></p>
          <button class="primary cta" id="submit" ${session.paymentMethods.length ? '' : 'disabled'}>${ctaLabel(session.paymentMethods[0])}</button>
          <p class="fine">${icon('shield')} Your details are used only to fulfil this order.</p>
          ${cancelUrl ? `<a class="back" href="${esc(cancelUrl)}">← Return to store</a>` : ''}
        </div>
      </section>
      ${trustHtml('trust-below')}
    </form>
    <div class="summary-col">${summaryHtml()}${trustHtml()}</div>`;
  document.querySelector('#checkout-form').addEventListener('submit', submitOrder);
  wirePaymentMethods();
  wireRegionPicker();
}

/** State/province is a list for countries that have one (US, Canada, Australia), a free text box otherwise. */
/** Free-shipping promotion banner under the total: shows what is left to spend, or that it is unlocked. */
function promoHtml() {
  const left = FREE_SHIPPING_FROM - session.subtotal;
  const text = left > 0
    ? `Spend <b>${money(FREE_SHIPPING_FROM)}</b> to unlock <b>free shipping</b> — add <b>${money(left)}</b> more`
    : `<b>Free shipping unlocked!</b> Your order is over ${money(FREE_SHIPPING_FROM)}`;
  return `<div class="promo ${left > 0 ? '' : 'unlocked'}">${icon('truck')}<span>${text}</span></div>`;
}

function wireRegionPicker() {
  const form = document.querySelector('#checkout-form');
  const field = form.querySelector('[data-role="state-field"]');
  const render = () => {
    const regions = regionsFor(form.elements.country.value);
    const previous = form.elements.state?.value ?? '';
    field.innerHTML = regions
      ? `<span class="req">State / Province</span><select name="state" autocomplete="address-level1" required>
           <option value="">Select</option>${regions.map((r) => `<option ${r === previous ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select>`
      : 'State / Province <span class="hint">(optional)</span><input name="state" autocomplete="address-level1">';
  };
  form.elements.country.addEventListener('change', render);
  render(); // a single-country list is preselected, so its state list is needed straight away
}

async function submitOrder(event) {
  event.preventDefault();
  const form = event.target;
  const value = (name) => form.elements[name].value.trim();
  const button = document.querySelector('#submit');
  const error = document.querySelector('#error');
  error.textContent = '';
  if (!value('country')) { error.textContent = 'Please select your country.'; form.elements.country.focus(); return; }
  if (form.elements.state.tagName === 'SELECT' && !value('state')) { error.textContent = 'Please select your state or province.'; form.elements.state.focus(); return; }
  const method = selectedMethod();
  const paying = method?.type === 'card';
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> ${paying ? 'Processing payment…' : 'Placing your order…'}`;
  try {
    let cardToken = '';
    if (paying) {
      if (!cardHandle) throw new Error('Card payments are unavailable right now. Please choose another payment method.');
      cardToken = await cardHandle.tokenize(); // throws a friendly message if the card details are incomplete
    }
    const response = await fetch(`/api/public/sessions/${encodeURIComponent(sessionId)}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer: { name: value('name'), email: value('email'), phone: value('phone') },
        shipping_address: {
          line1: value('line1'), line2: value('line2'), city: value('city'),
          state: value('state'), postal_code: value('postal_code'), country: value('country'),
        },
        payment_method: method?.id,
        card_token: cardToken,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Something went wrong');
    const payUrl = result.redirect_url && safeHttpUrl(result.redirect_url);
    if (payUrl) { // redirect card flow: finish paying on the client's page
      button.innerHTML = '<span class="spinner"></span> Redirecting to secure payment…';
      location.assign(payUrl);
      return;
    }
    showConfirmation(result.order_number, result.success_url, result.payment_instructions);
  } catch (err) {
    error.textContent = err.message;
    error.scrollIntoView({ block: 'center', behavior: 'smooth' });
    button.disabled = false;
    button.textContent = ctaLabel();
  }
}

// ---------------------------------------------------------------- confirmation
function chip(label, value) {
  return `<span class="chip">${label} <b>${esc(value)}</b><button type="button" data-copy="${esc(value)}">${icon('copy')} Copy</button></span>`;
}

function showConfirmation(orderNumber, successUrl, paymentInstructions, paymentUrl = '') {
  const url = safeHttpUrl(successUrl);
  const payAgain = safeHttpUrl(paymentUrl);
  const owing = Boolean(paymentInstructions);
  setStepper(3); // all steps complete
  app.className = 'layout single';
  app.innerHTML = `
    <section class="confirmation">
      <div class="burst"><svg viewBox="0 0 92 92" aria-hidden="true"><circle class="ring" cx="46" cy="46" r="46" transform="rotate(-90 46 46)"/><path class="tick" d="M28 47.5 41 60.5 65 34"/></svg></div>
      <h2>${payAgain ? `Order #${esc(orderNumber)} is waiting for payment.` : `Thank you! Order #${esc(orderNumber)} is placed.`}</h2>
      <p class="lead">${payAgain ? "Your payment hasn't been confirmed yet. Continue to the secure payment page to finish." : owing ? "Just one more step: send your payment and we'll take it from there." : "We've emailed your receipt and will keep you posted."}</p>
      <div class="chips">${chip('Order', `#${orderNumber}`)}${owing ? chip('Amount', money(session.total)) : ''}</div>
      ${owing && !payAgain ? `<div class="pay-box"><h3>${icon('transfer')} Complete your payment</h3><p>${esc(paymentInstructions)}</p></div>` : ''}
      ${payAgain ? `<a class="cta-link" href="${esc(payAgain)}">Continue to payment</a>` : ''}
      ${noticeHtml()}
      <ol class="timeline">
        <li class="ok"><span class="n">${icon('check')}</span><div><b>Order placed</b>Your order is saved${owing ? '' : ' and paid'}.</div></li>
        <li><span class="n">2</span><div><b>${owing ? 'Send your payment' : 'We prepare your order'}</b>${owing ? 'Use your order number so we can match it.' : 'You will get a shipping update by email.'}</div></li>
        <li><span class="n">3</span><div><b>${owing ? 'We confirm and ship' : 'On its way'}</b>${owing ? "We'll email you as soon as your payment arrives." : 'Tracking details follow once shipped.'}</div></li>
      </ol>
      ${url ? `<a class="cta-link" href="${esc(url)}">Continue</a>` : ''}
    </section>`;

  app.querySelectorAll('[data-copy]').forEach((button) =>
    button.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(button.dataset.copy); } catch { /* clipboard unavailable */ }
      button.classList.add('copied');
      button.innerHTML = `${icon('check')} Copied`;
      setTimeout(() => { button.classList.remove('copied'); button.innerHTML = `${icon('copy')} Copy`; }, 1800);
    }));
}

// Coming back with the browser's Back button can restore the page frozen on "Redirecting…": start over from the saved state.
window.addEventListener('pageshow', (event) => { if (event.persisted) location.reload(); });

init().catch(() => showMessage({ iconName: 'x-circle', title: 'Something went wrong', text: 'Please refresh and try again.' }));
