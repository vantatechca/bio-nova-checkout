# Redirect payment: integration steps

When the customer presses Pay, our checkout calls your endpoint, then sends the customer to the payment page you return. After they pay, your server tells our API the order is paid.

How it runs:
1. The customer presses Pay on our checkout.
2. Our checkout sends a signed create_payment request to your endpoint.
3. Your endpoint creates a payment page and replies with its redirect_url.
4. The customer's browser is sent to that redirect_url and pays there.
5. Your payment page sends the customer's browser back to our return_url.
6. Your server marks the order paid with PATCH /api/v1/orders/{order_id}.

A complete working example of steps 1 to 4 below is in the attached file redirect_payment_api.py.

## Step 1. Receive our request
`POST` to your endpoint URL. The same URL receives every request type, told apart by `type` in the body.

Headers

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-Checkout-Timestamp` | Unix time in seconds when the request was signed |
| `X-Checkout-Signature` | `sha256=` + hex HMAC-SHA256 of `"<timestamp>.<raw request body>"`, keyed with the signing secret |
| `Idempotency-Key` | The checkout session id (same as `reference`). Identical on every retry of the same payment |

Body (`type: "create_payment"`)
```json
{
  "type": "create_payment",
  "reference": "cs_9f3c0b…",
  "order_ref": "cart_123",
  "amount": 6500,
  "currency": "USD",
  "description": "Order from My Store",
  "customer": { "name": "Ada Lovelace", "email": "ada@example.com", "phone": "" },
  "shipping_address": { "line1": "1 Main St", "line2": "", "city": "Toronto", "state": "ON", "postal_code": "M5V 1A1", "country": "CA" },
  "items": [ { "name": "Shirt", "sku": "SH-1", "quantity": 2, "unit_amount": 2500 } ],
  "return_url": "https://checkout.example.com/checkout?session=cs_9f3c0b…",
  "cancel_url": "https://checkout.example.com/checkout?session=cs_9f3c0b…"
}
```
`amount` and `unit_amount` are in minor units (cents). `order_ref` is empty when the store sent none.

Verify the signature first:
1. Reject if `abs(now - X-Checkout-Timestamp) > 300` seconds.
2. Compute `sha256=` + `HMAC_SHA256(signing_secret, timestamp + "." + raw_body)` over the raw body bytes (before JSON parsing) and compare with `X-Checkout-Signature` using a constant-time comparison.
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

Health check: the admin's "Save & test client API" button sends `{"type": "ping"}` (signed the same way). Reply `200 {"ok": true}`.

## Step 2. Reply with the payment page
```json
{ "status": "redirect", "redirect_url": "https://pay.client.example/p/abc123", "id": "pay_abc123" }
```

| Outcome | HTTP | Body |
|---|---|---|
| Payment page created | `200` | the JSON above |
| Bad signature | `401` | anything |
| Error on your side | `5xx` | anything (the customer sees a generic "try again" message) |

- `redirect_url` must be `https`.
- `id` is optional and is stored on our order as the payment reference.
- The same `Idempotency-Key` returns the same payment page.

## Step 3. Send the customer back
After the customer pays or cancels, send their browser to `return_url` or `cancel_url`.

## Step 4. Mark the order paid
When your processor confirms the payment, call our API from your server (use the processor's webhook as the trigger). Every call needs `Authorization: Bearer <API key>`.

4a. Find our order from the `reference` you received
```
GET https://checkout.example.com/api/v1/checkout/sessions/{reference}
```
Reply (shortened):
```json
{
  "id": "cs_9f3c0b…",
  "status": "complete",
  "currency": "USD",
  "total": 6500,
  "external_ref": "cart_123",
  "order_id": "ord_4d1e2a9c7b3f5a60",
  "checkout_url": "https://checkout.example.com/checkout?session=cs_9f3c0b…"
}
```
`order_id` is `null` until the customer has pressed Pay.

4b. Mark it paid
```
PATCH https://checkout.example.com/api/v1/orders/{order_id}
Content-Type: application/json

{ "payment_status": "paid", "payment_reference": "ch_123" }
```
Reply (shortened):
```json
{
  "id": "ord_4d1e2a9c7b3f5a60",
  "number": 1042,
  "status": "processing",
  "payment_status": "paid",
  "payment_reference": "ch_123",
  "total": 6500,
  "paid_at": "2026-11-09T14:02:11Z"
}
```
Other values for `payment_status`: `failed`, `refunded`.

Errors from our API are JSON `{"error": "<message>"}`:

| HTTP | Meaning |
|---|---|
| `401` | `"Invalid or missing API key"` |
| `404` | session or order not found |
| `400` | a field in your request has an invalid value; the message names the field |

Calling the `PATCH` again with the same values is safe.
