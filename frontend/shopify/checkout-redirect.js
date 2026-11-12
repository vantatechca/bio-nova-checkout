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
 * "Buy it now" on product pages: Shopify's accelerated checkout buttons (Shop Pay / Apple Pay / "Buy it now") bypass this
 * checkout, so they are hidden and replaced by our own "Buy it now" button, which checks out just that product
 * (the variant and quantity chosen on the page) without touching the cart. A theme's own custom buy-now button can be
 * wired up by adding the attribute  data-checkout-buy-now  to it; buttons labelled "Buy it now" / "Buy now" are
 * picked up automatically.
 *
 * Add  data-keep-dynamic-buttons  to the <script> tag to leave Shopify's buttons as they are
 * (no replacement; they bypass this checkout).
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

  var BUY_NOW_LABEL = 'Buy it now';
  var BUY_NOW = '[data-checkout-buy-now]';

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
    if (el) setLoading(el, false);
    window.alert(message || 'Sorry, checkout is unavailable right now. Please try again in a moment.');
  }

  function post(cartToken, items) {
    return fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cart_token: cartToken,
        shop: (window.Shopify && window.Shopify.shop) || '', // tells the checkout which of its stores this is
        items: items
      })
    }).then(function (r) {
      return r.json().then(function (body) { return { ok: r.ok, body: body }; });
    });
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
        return post(cart.token || '', cart.items.map(function (item) { return { variant_id: item.variant_id, quantity: item.quantity }; }));
      })
      .then(finish.bind(null, trigger))
      .catch(function () { fail(trigger); });
  }

  // "Buy it now": check out only the product on this page (the form's current variant and quantity).
  function buyNow(trigger) {
    if (busy) return;
    var form = trigger.closest('form[action*="/cart/add"]') || document.querySelector('form[action*="/cart/add"]');
    var data = form ? new FormData(form) : null;
    var variant = parseInt((data && data.get('id')) || new URLSearchParams(location.search).get('variant'), 10);
    if (!variant) return fail(null, 'Please choose an option first.');
    var qtyInput = (data && data.get('quantity')) || (document.querySelector('input[name="quantity"]') || {}).value;
    var quantity = Math.max(1, parseInt(qtyInput, 10) || 1);
    busy = true;
    setLoading(trigger, true);
    post('', [{ variant_id: variant, quantity: quantity }])
      .then(finish.bind(null, trigger))
      .catch(function () { fail(trigger); });
  }

  function finish(trigger, result) {
    if (!result) return;
    if (result.ok && result.body.checkout_url) window.location.assign(result.body.checkout_url);
    else fail(trigger, result.body && result.body.error);
  }

  // A theme's own "Buy it now" button (not Shopify's dynamic one): recognised by its label.
  function isBuyNowButton(el) {
    if (!el || el.closest(CHECKOUT_TRIGGER)) return false;
    var label = (el.tagName === 'INPUT' ? el.value : el.textContent) || '';
    return /^\s*buy\s*(it\s*)?now\s*$/i.test(label);
  }

  // Product pages with Shopify's accelerated buttons get our own "Buy it now" button right where they were.
  function addBuyNowButtons() {
    if (script.hasAttribute('data-keep-dynamic-buttons')) return;
    document.querySelectorAll('.shopify-payment-button, [data-shopify="payment-button"]').forEach(function (anchor) {
      var form = anchor.closest('form[action*="/cart/add"]');
      if (!form || form.querySelector(BUY_NOW)) return;
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'button button--full-width button--secondary btn btn--secondary';
      button.setAttribute('data-checkout-buy-now', '');
      button.textContent = BUY_NOW_LABEL;
      button.style.width = '100%';
      button.style.marginTop = '10px';
      anchor.parentNode.insertBefore(button, anchor);
    });
  }
  addBuyNowButtons();
  document.addEventListener('DOMContentLoaded', addBuyNowButtons);
  // Themes that re-render the product form (variant change, quick view) lose the button: put it back.
  new MutationObserver(addBuyNowButtons).observe(document.documentElement, { childList: true, subtree: true });

  // Capture phase, so we run before the theme's own handlers and Shopify's default navigation.
  document.addEventListener('click', function (event) {
    var now = event.target.closest && event.target.closest(BUY_NOW);
    if (!now && !script.hasAttribute('data-keep-dynamic-buttons') && event.target.closest) {
      var candidate = event.target.closest('button, a, input[type="submit"], input[type="button"], [role="button"]');
      if (isBuyNowButton(candidate)) now = candidate;
    }
    if (now) {
      event.preventDefault();
      event.stopImmediatePropagation();
      buyNow(now);
      return;
    }
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
