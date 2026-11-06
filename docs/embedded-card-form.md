# Embedded card form (processor-agnostic)

Use this when the client has their own payment processor (or several, or one that changes over time) and you do not want
processor-specific code in the checkout. The client hosts **two things**; the checkout never needs their processor keys:

| # | What the client hosts | Purpose |
|---|---|---|
| 1 | **Card form page** (this document) | Shown inside the checkout in an iframe. The customer types the card here; it goes to the client's processor and a **token** comes back. |
| 2 | **Charge endpoint** ([client-payment-api.md](client-payment-api.md)) | Receives the token from our server (signed), charges it with the processor's secret key, answers `succeeded` / `declined`. |

Because both live on the client's side, switching processor means changing **their** two pieces only. Nothing changes in the
checkout, and nothing is redeployed here.

```
 customer's browser (our checkout page)                         client's servers
 ──────────────────────────────────────                         ────────────────
  ┌─ iframe: client's card form page ─┐
  │ card number ───────────────────────┼──────────────────────►  client's processor  (token)
  └────────────────────────────────────┘
        ▲  postMessage: tokenize / token
  our checkout JS
        │ token + order details
        ▼
  our server ── signed POST /charge ───────────────────────────►  client's endpoint ─► processor
        ◄─────────────── { status: "succeeded", id } ───────────
  order marked Paid
```

The card number never reaches our page, JavaScript or server. Only the iframe (the client's origin) sees it.

## Setup (admin)

**Settings → Card payments**
1. *Card fields provider*: **Client-hosted card form**.
2. *Client's card form URL*: the https URL of the page below (plain `http` is accepted for `localhost` only).
3. *Client's charge API URL*: their `/charge` endpoint.
4. Give the client the **signing secret**, press **Save & test client API**, then **Add "Credit card" payment method**.

## What the client's card form page must do

It is an ordinary web page. It must:

1. Render the processor's own hosted card fields (Stripe Elements, Adyen, Authorize.net Accept.js, NMI Collect.js,
   Checkout.com Frames …) so the card number never touches the client's own code either.
2. Allow being framed by the checkout: send `Content-Security-Policy: frame-ancestors https://YOUR-CHECKOUT-DOMAIN`
   (and no `X-Frame-Options: DENY`).
3. Talk to the checkout with `postMessage`, as below.

### Messages

All messages are objects with a `source` field. Always check `event.origin` against the checkout's origin and send with an
explicit target origin, never `"*"`.

**Form → checkout**

| Message | When |
|---|---|
| `{ source: "checkout-card-form", type: "ready" }` | As soon as the fields are loaded and usable. The checkout waits up to 15 s for it, then shows "card payments unavailable". |
| `{ source: "checkout-card-form", type: "height", height: 240 }` | Optional. Resize the iframe (80–900 px). Send again whenever the form grows (e.g. validation errors). |
| `{ source: "checkout-card-form", type: "token", id, token }` | Reply to `tokenize`. `id` is copied from the request. `token` is the single-use processor token (max 500 characters). |
| `{ source: "checkout-card-form", type: "error", id, message }` | Reply to `tokenize` when the card is incomplete or invalid. `message` is shown to the customer (max 200 characters): keep it short and safe, e.g. "Your card number is incomplete." |

**Checkout → form**

| Message | When |
|---|---|
| `{ source: "checkout", type: "tokenize", id }` | The customer pressed Pay. Create the token and answer with `token` or `error` (within 60 s). |

### Minimal page

```html
<!doctype html>
<meta charset="utf-8">
<div id="card-fields"></div>
<script>
  const CHECKOUT_ORIGIN = 'https://checkout.example.com';          // our checkout's origin

  // 1) mount the processor's hosted fields (processor-specific, this is the only part that changes)
  const processor = await mountProcessorFields('#card-fields');     // e.g. stripe.elements().create('payment')

  // 2) tell the checkout we are ready
  parent.postMessage({ source: 'checkout-card-form', type: 'ready' }, CHECKOUT_ORIGIN);

  // 3) create a token when asked
  addEventListener('message', async (event) => {
    if (event.origin !== CHECKOUT_ORIGIN || event.source !== parent) return;
    const msg = event.data;
    if (msg?.source !== 'checkout' || msg.type !== 'tokenize') return;
    try {
      const token = await processor.createToken();                  // processor-specific
      parent.postMessage({ source: 'checkout-card-form', type: 'token', id: msg.id, token }, CHECKOUT_ORIGIN);
    } catch (err) {
      parent.postMessage({ source: 'checkout-card-form', type: 'error', id: msg.id, message: err.message }, CHECKOUT_ORIGIN);
    }
  });
</script>
```

A runnable version with a fake tokenizer is in [`examples/embedded_card_form.html`](../examples/embedded_card_form.html).

## Rules that keep it safe

- Never send, log or store card numbers anywhere except the processor's fields. Only the processor's token leaves the form.
- Tokens are single-use; create a new one for every `tokenize` request.
- Verify `event.origin` and use an explicit `targetOrigin`.
- 3-D Secure / extra authentication is not supported yet: the charge endpoint should answer `declined` (or run the
  authentication inside the card form before returning the token, if the processor supports that).
- Before going live the client's processor must approve taking payments through the checkout's domain — get that in
  writing. See the going-live checklist in [client-payment-api.md](client-payment-api.md).

## Changing processor later

Swap the SDK inside the card form page and the processor calls inside the charge endpoint. The message format, the signing
contract and the settings here stay exactly the same.
