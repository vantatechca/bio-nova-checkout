# Connecting the checkout: start guide

## Access
| Item | Use |
|---|---|
| Checkout and admin | `https://bio-nova-checkout.onrender.com` (admin at `/admin`) |
| Admin password | log in to see orders and each order's timeline |
| API key (`sk_…`) | send as `Authorization: Bearer <key>` on calls to our API |
| Signing secret (`capi_…`) | verify the signature on requests we send to your endpoint |

Interactive API reference: `https://bio-nova-checkout.onrender.com/api/docs`

## What you build
1. One endpoint that receives our signed `create_payment` request and replies with your payment page URL.
2. A call to our API when a payment succeeds: look up the order, then mark it paid.

Everything is in [redirect-payment.md](redirect-payment.md): request format, signature check (Python and Node), replies, the calls to our API with sample responses, and error codes.

A complete working example is in the attached file redirect_payment_api.py.

## Our API
All calls need `Authorization: Bearer <API key>`.

| Call | Use |
|---|---|
| `POST /api/v1/checkout/sessions` | create a checkout session |
| `GET /api/v1/checkout/sessions/{id}` | read a session, including `order_id` |
| `GET /api/v1/orders` | list orders (`?external_ref=` to find one by your reference) |
| `GET /api/v1/orders/{id or number}` | read one order |
| `PATCH /api/v1/orders/{id or number}` | set `payment_status` to `paid`, `failed` or `refunded` |

## First test
1. Create a session with `POST /api/v1/checkout/sessions` and open the returned `checkout_url`:
   ```json
   { "items": [ { "name": "Test product", "unit_amount": 2500, "quantity": 2 } ],
     "customer": { "name": "Test Customer", "email": "test@example.com" },
     "success_url": "https://example.com/thanks" }
   ```
2. Fill the form, choose Credit card, press Pay. Your endpoint receives the signed request.
3. Pay on your page. Your server then marks the order paid.
4. The order in our admin moves from Pending to Processing.
