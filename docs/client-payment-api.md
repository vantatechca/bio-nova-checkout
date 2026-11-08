# Client payment API

How the hosted checkout charges a card through **your** payment processor, without the card number ever touching
the checkout server.

```
 customer's browser                        checkout server                      your server (this API)         your processor
 ──────────────────                        ───────────────                      ──────────────────────         ──────────────
 types card into the processor's  ───────────────────────────────────────────────────────────────────────────►  gives back a token
 own hosted fields (no card data
 in our code or on our server)
        │ token
        ▼
 POST /api/public/sessions/…/complete ──►  POST <your charge URL>  ──────────►  verify signature ─► charge token ─►  approve / decline
   { …order details…, card_token }          signed JSON, see below              reply JSON  ◄──────────────────────
                                            ◄────────── { status, id }
 order marked paid (or the decline shown to the customer)
```

* Cards are entered in the **processor's hosted fields** (Stripe Elements, Authorize.net Accept.js, NMI Collect.js …),
  so the card number goes browser → processor only. This keeps the checkout page and server out of the heavy PCI scope
  (you are responsible for confirming your processor's requirements).
* **You** keep your processor's secret keys. The checkout only holds the processor's *publishable* key and a shared
  *signing secret* used to authenticate its requests to you.
* Your endpoint **must be https** (plain http is only accepted for `localhost` while developing).

## What you build: one endpoint

`POST <your charge URL>` — the URL is entered in the checkout admin (Settings → Card payments).

### Request

Headers

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-Checkout-Timestamp` | Unix time in seconds when the request was signed |
| `X-Checkout-Signature` | `sha256=` + hex **HMAC-SHA256** of the string `"<timestamp>.<raw request body>"`, keyed with the signing secret |
| `Idempotency-Key` | The checkout session id (also in `reference`). Identical for every retry of the same payment |

Body (`type: "charge"`)

```json
{
  "type": "charge",
  "reference": "cs_9f3c0b…",          // checkout session id; use it to de-duplicate
  "order_ref": "cart_123",            // the store's own cart/order id, if it sent one
  "amount": 5500,                     // integer, minor units (cents)
  "currency": "USD",
  "token": "tok_…",                   // single-use token from the processor's card fields
  "description": "Order from My Store",
  "customer": { "name": "Ada Lovelace", "email": "ada@example.com", "phone": "" },
  "shipping_address": { "line1": "1 Main St", "line2": "", "city": "Toronto", "state": "ON", "postal_code": "M5V 1A1", "country": "CA" },
  "items": [ { "name": "Shirt", "sku": "SH-1", "quantity": 2, "unit_amount": 2500 } ]
}
```

A health check is sent from the admin ("Save & test client API"): body `{"type": "ping"}` — answer `200 {"ok": true}`.

### Verifying the request (do this first!)

1. Reject if `abs(now - X-Checkout-Timestamp) > 300` seconds (stops replays).
2. Compute `sha256=` + `HMAC_SHA256(signing_secret, timestamp + "." + raw_body)` over the **raw** body bytes (before
   JSON parsing) and compare with `X-Checkout-Signature` using a **constant-time** comparison.
3. Reject with `401` if either check fails.

Python

```python
import hashlib, hmac, time


def verify(secret: str, timestamp: str, raw_body: bytes, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Node

```js
const crypto = require('crypto');
function verify(secret, timestamp, rawBody, signature) {
  if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) return false;
  const expected = 'sha256=' + crypto.createHmac('sha256', secret).update(`${timestamp}.${rawBody}`).digest('hex');
  return signature.length === expected.length && crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}
```

### Response

Always JSON.

| Outcome | HTTP | Body |
|---|---|---|
| Charged | `200` | `{"status": "succeeded", "id": "<processor charge id>"}` |
| Card declined | `200` | `{"status": "declined", "message": "Your card has insufficient funds."}` — the message is shown to the customer, keep it short and safe |
| Bad signature | `401` | anything |
| Your/processor error | `5xx` | anything (the customer sees a generic "try again" message) |

* `id` is stored on the order as its payment reference — use the processor's charge/transaction id.
* **Idempotency is required — for successful charges.** If a request arrives with an `Idempotency-Key` that has
  already been charged successfully (the checkout retries when it doesn't hear back, and a customer may click again),
  return that **same success** and do **not** charge again — even if the retry carries a different token.
  **Do not remember declines or errors:** after a decline the customer may try another card on the same checkout, and
  that request carries the same key and must be processed normally.
* Charge exactly `amount` in `currency`. If you can, also check it against your own records.
* 3-D Secure / extra authentication (`requires_action`) is **not supported yet**: answer `declined`, or `5xx`.
* Refunds are made in your processor's dashboard; then mark the order refunded in the checkout admin.

## Testing

1. **Reference implementation:** [`examples/client_payment_api.py`](../examples/client_payment_api.py) is a complete,
   tested example of this endpoint (FastAPI). Run it with
   `SIGNING_SECRET=capi_… uvicorn examples.client_payment_api:app --port 9000`.
2. In the admin set **Client's charge API URL** to `http://localhost:9000/charge` (plain http is allowed for localhost),
   choose the **Test provider**, add the **Card** payment method, and press **Save & test client API**.
3. At checkout use the test provider's cards: `4242 4242 4242 4242` succeeds, `4000 0000 0000 0002` is declined.

## Going live checklist

- [ ] Your endpoint is https, verifies signature + timestamp, and is idempotent.
- [ ] The signing secret is stored as a secret on your server (never in browser code) and rotated if it leaks
      (Settings → Card payments → Rotate, then update your server).
