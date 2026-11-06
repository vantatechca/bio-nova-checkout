/*
 * Shopify → hosted checkout redirect.
 *
 * Add ONE line to your Shopify theme (Online Store → Themes → Edit code → layout/theme.liquid, just before </body>):
 *
 *   <script src="https://YOUR-CHECKOUT-DOMAIN/static/shopify/checkout-redirect.js" defer></script>
 *
 * When a shopper clicks "Checkout" (cart page or cart drawer) this sends their cart's variant ids + quantities to the
 * checkout service, which looks up the real prices from Shopify and replies with the checkout page to open.
 * Prices are never read from the browser, so they can't be tampered with.
 *
 * Add  data-keep-dynamic-buttons  to the <script> tag to leave Shop Pay / Apple Pay buttons visible
 * (they bypass this checkout, so they are hidden by default).
 */
(function () {
  'use strict';

  var script = document.currentScript;
  if (!script || !script.src) return;
  var endpoint = new URL('/api/shopify/checkout', script.src).href;
  var busy = false;

  // Shopify's accelerated checkout buttons go straight to Shopify's checkout, so hide them.
  if (!script.hasAttribute('data-keep-dynamic-buttons')) {
    var style = document.createElement('style');
    style.textContent = '.shopify-payment-button, .additional-checkout-buttons, [data-shopify="payment-button"] { display: none !important; }';
    document.head.appendChild(style);
  }

  var CHECKOUT_TRIGGER = [
    '[name="checkout"]',
    'a[href="/checkout"]',
    'a[href^="/checkout?"]',
    'a[href^="/checkout/"]',
    'form[action="/checkout"] [type="submit"]'
  ].join(',');

  function setLoading(el, loading) {
    if (!el) return;
    if (loading) {
      el.dataset.originalText = el.value || el.textContent;
      if ('disabled' in el) el.disabled = true;
      el.style.opacity = '0.7';
      if ('value' in el && el.tagName === 'INPUT') el.value = 'Redirecting…';
      else el.textContent = 'Redirecting…';
    } else {
      if ('disabled' in el) el.disabled = false;
      el.style.opacity = '';
      if (el.dataset.originalText) {
        if (el.tagName === 'INPUT') el.value = el.dataset.originalText;
        else el.textContent = el.dataset.originalText;
      }
    }
  }

  function fail(el, message) {
    busy = false;
    setLoading(el, false);
    window.alert(message || 'Sorry, checkout is unavailable right now. Please try again in a moment.');
  }

  function startCheckout(trigger) {
    if (busy) return;
    busy = true;
    setLoading(trigger, true);

    fetch('/cart.js', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (cart) {
        if (!cart.items || !cart.items.length) {
          busy = false;
          setLoading(trigger, false);
          return null;
        }
        return fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            cart_token: cart.token || '',
            items: cart.items.map(function (item) { return { variant_id: item.variant_id, quantity: item.quantity }; })
          })
        }).then(function (r) {
          return r.json().then(function (body) { return { ok: r.ok, body: body }; });
        });
      })
      .then(function (result) {
        if (!result) return;
        if (result.ok && result.body.checkout_url) window.location.assign(result.body.checkout_url);
        else fail(trigger, result.body && result.body.error);
      })
      .catch(function () { fail(trigger); });
  }

  // Capture phase, so we run before the theme's own handlers and Shopify's default navigation.
  document.addEventListener('click', function (event) {
    var trigger = event.target.closest && event.target.closest(CHECKOUT_TRIGGER);
    if (!trigger) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    startCheckout(trigger);
  }, true);

  // Pressing Enter inside the cart form submits it with the "Checkout" button as the submitter.
  document.addEventListener('submit', function (event) {
    var submitter = event.submitter;
    var form = event.target;
    var isCheckout = (submitter && submitter.name === 'checkout') || (form.getAttribute && form.getAttribute('action') === '/checkout');
    if (!isCheckout) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    startCheckout(submitter);
  }, true);

  // Coming back with the browser's Back button restores the page as it was: undo the "Redirecting…" state.
  window.addEventListener('pageshow', function (event) {
    if (event.persisted) {
      busy = false;
      document.querySelectorAll('[data-original-text]').forEach(function (el) { setLoading(el, false); });
    }
  });
})();
