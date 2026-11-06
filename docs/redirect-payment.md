# Redirect to the client's payment page

The alternative to the [embedded card form](embedded-card-form.md). When the customer picks **Credit card** and presses
**Pay**, the checkout asks the client's API for a payment page and sends the customer there. The customer enters the card
on the client's page (their processor's hosted page), and the client tells us when the order is paid.

Same endpoint URL and the same signing as the [charge API](client-payment-api.md); only the `type` of the request differs.

```
 customer              our checkout                    client's API (same URL as /charge)         client's payment page
 ────────              ────────────                    ─────────────────────────────────          ─────────────────────
 presses Pay ───────►  POST type:"create_payment" ───►  creates a payment page for this order
                       ◄──── { status:"redirect", redirect_url } ──
 ◄──── browser is sent to redirect_url ───────────────────────────────────────────────────────►   customer pays here
 ◄──── browser is sent back to return_url (our checkout) ◄────────────────────────────────────
                                      client's server ── PATCH /api/v1/orders/{number} ──►  our order becomes PAID
 our page shows "Thank you" as soon as the order is paid
```

The order is created **pending** right away and stays pending until the client marks it paid.

## Setup (admin)
**Settings → Card payments**: provider **Redirect to the client's payment page**, *Client's charge API URL* = their endpoint.
Give them the signing secret and the **API key** (Settings), then add the **Credit card** payment method.

## 1. What we send (`POST`, signed exactly like a charge)
Headers: `Content-Type`, `X-Checkout-Timestamp`, `X-Checkout-Signature`, `Idempotency-Key` (the checkout session id) — see
[client-payment-api.md](client-payment-api.md#request) for how to verify them.

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
There is no `token`: no card data is involved on our side at all. `amount` is in minor units (cents).

## 2. What you reply
```json
{ "status": "redirect", "redirect_url": "https://pay.client.example/p/abc123", "id": "pay_abc123" }
```
- `redirect_url` must be **https** (plain http only for `localhost`). Anything else is refused and the customer sees a
  "payment temporarily unavailable" message.
- `id` is optional; it is stored on our order as the payment reference.
- The same `Idempotency-Key` should give back the same (or an equivalent) payment page.
- Errors: `401` for a bad signature, `5xx` if something is wrong on your side (the customer sees a generic "try again").

## 3. Send the customer back
After the customer pays (or cancels), send their browser to `return_url` / `cancel_url`. Our page then shows the order and,
if it is already paid, the confirmation. If it isn't paid yet, our page keeps checking for about two minutes.

## 4. Tell us the order is paid (required)
Our order only becomes **paid** when you tell us. Call our store API from **your server** (never from the browser):

1. **Find our order.** You were sent our session id as `reference`. Look it up to get the order id:
   ```
   GET https://checkout.example.com/api/v1/checkout/sessions/{reference}
   Authorization: Bearer <our API key>
   ```
   The reply has `"order_id": "ord_…"` (it is `null` until the customer has pressed Pay). If the store sent an `external_ref`,
   `GET /api/v1/orders?external_ref=<order_ref>` also finds it.
2. **Mark it paid.**
   ```
   PATCH https://checkout.example.com/api/v1/orders/{order_id}
   Authorization: Bearer <our API key>
   Content-Type: application/json

   { "payment_status": "paid", "payment_reference": "ch_123" }
   ```
- Use your processor's **webhook** ("payment succeeded") to trigger this call; do not trust the customer's browser return.
- Other values: `"payment_status": "failed"` or `"refunded"`. `"notify": false` skips the customer email for a change.
- Marking an order paid moves it to *processing* and sends the usual emails.

## Notes
- Until the PATCH arrives the order shows as **Pending** in our admin; you can also mark it paid by hand there.
- If the customer never pays, the pending order simply stays pending.
- Their processor must approve taking payments for the client through this checkout flow — see the going-live checklist
  in [client-payment-api.md](client-payment-api.md).
