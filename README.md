# Hosted Checkout + Order Admin

A hosted checkout page, an order-management admin and a REST API you connect your store to. Your store sends
the cart to the API, gets back a `checkout_url`, and redirects the customer there. Staff manage the orders
(including manual payments that are confirmed by hand) in `/admin`.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · MySQL 8 · Alembic · plain HTML/CSS/ES-modules frontend (no build step).

## Quick start

### Docker (app + MySQL)

```bash
ADMIN_PASSWORD=change-me docker compose up --build
# admin:    http://localhost:3000/admin
# API docs: http://localhost:3000/api/docs
```

### Local development

```bash
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                                  # set DB_* and ADMIN_PASSWORD
python -m app                                         # creates the database + tables on first start
```

Need a throwaway MySQL? `docker run -d --name checkout-mysql -e MYSQL_ROOT_PASSWORD=secret -p 3306:3306 mysql:8.4`
then set `DB_PASSWORD=secret`.

Your **API key**, webhook secret, payment methods, shipping/tax defaults and SMTP settings are in
**Admin → Settings & API / Email**. All configuration options are listed in [.env.example](.env.example).

## Several stores, one checkout

One deployment can serve any number of stores. **Admin → Stores → Add a store** creates one; each store has its own:
API key, branding (logo, menu links, notice), payment/card setup, shipping & tax defaults, webhook URL + secret and Shopify
connection. Orders, checkout sessions and visits are stored per store; a store's API key only ever reaches that store's data.

- The **store switcher** in the sidebar filters orders, revenue and visits to one store (or *All stores*). *Settings & API*
  always edits the selected store.
- Disabling a store stops its API key and Shopify button working; stores that have orders can be disabled but not deleted.
- Each store needs its own website / Shopify domain (two stores can't claim the same one).
- Shared across stores: the admin login, SMTP/email settings, and the order-number sequence (#1001, #1002, … is global).
- Upgrading a single-store install is automatic: its settings become store #1 and keep the same API key, so existing
  integrations continue to work.

## How a store connects

1. Customer clicks checkout on your store.
2. Your **server** calls `POST /api/v1/checkout/sessions` with the cart → response contains `checkout_url`.
3. Redirect the customer to `checkout_url`. They enter their details and place the order.
4. They are sent back to your `success_url` with `?checkout_session=…&order=1001&ref=<external_ref>`.
5. Your server receives `order.created` (and `order.paid` / `order.updated`) webhooks.

Build the cart on **your server** from your own catalog — never trust prices sent from the browser.

## API (server-to-server)

Auth: `Authorization: Bearer <API key>` (or `X-API-Key`). Amounts are integers in minor units (cents).
Interactive docs: `/api/docs`. Errors are `{"error": "message"}` with a 4xx status.

### `POST /api/v1/checkout/sessions`
```json
{
  "items": [{ "name": "Shirt", "unit_amount": 2500, "quantity": 2, "sku": "SH-1", "image": "https://…", "description": "Size M" }],
  "currency": "USD",
  "success_url": "https://yourstore.com/thanks",
  "cancel_url": "https://yourstore.com/cart",
  "external_ref": "cart_123",
  "customer": { "name": "Ada", "email": "ada@example.com" },
  "shipping_amount": 500,
  "tax_amount": 400,
  "metadata": { "anything": "you want back" }
}
```
`success_url` is required; `shipping_amount` / `tax_amount` default to the values in Settings. Returns `201` with the
session including `checkout_url`. Sessions expire after 24 h (`SESSION_TTL_HOURS`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/checkout/sessions/{id}` | Session status (`open`, `complete`, `expired`) and `order_id` |
| GET | `/api/v1/orders?external_ref=cart_123` | List / find orders (latest 100) |
| GET | `/api/v1/orders/{id or number}` | One order |
| PATCH | `/api/v1/orders/{id or number}` | `status`, `payment_status`, `payment_reference`, `tracking_number`, `notes`, `notify` |

Order `status`: pending, processing, shipped, completed, cancelled, refunded.
`payment_status`: pending, paid, failed, refunded. Set `"notify": false` to skip the customer email for a change.

### Node example

```js
const r = await fetch("https://checkout.example.com/api/v1/checkout/sessions", {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.CHECKOUT_API_KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({
    items: cart.map((i) => ({ name: i.title, unit_amount: Math.round(i.price * 100), quantity: i.qty })),
    success_url: "https://yourstore.com/thanks", cancel_url: "https://yourstore.com/cart", external_ref: cart.id,
  }),
});
res.redirect((await r.json()).checkout_url);
```

## Connecting a Shopify store

Shoppers who click **Checkout** on your Shopify store are redirected to this checkout. Orders are then managed in this admin
(they are not created in Shopify).

1. **Token:** Shopify admin → *Settings → Apps and sales channels → Develop apps → Create an app*. Under *Configuration →
   Storefront API* tick `unauthenticated_read_product_listings`, install the app and copy the **Storefront API access token**.
2. **This admin → Settings → Shopify:** enter the shop domain (`your-shop.myshopify.com`) and the token, set **Store website**
   under *Branding*, then press **Save & test connection**.
3. **Theme:** *Online Store → Themes → Edit code → `layout/theme.liquid`*, just before `</body>`:
   ```html
   <script src="https://YOUR-CHECKOUT-DOMAIN/static/shopify/checkout-redirect.js" defer></script>
   ```
4. Turn off dynamic checkout buttons (Shop Pay, Apple Pay) if your theme shows them; the script hides the usual ones.

The same one-line script works for every store: the checkout recognises which store a cart belongs to from the page's origin
(its *Store website*) or, failing that, the `Shopify.shop` domain the script reports. With a single store nothing needs matching.

How it works: the script sends only variant ids and quantities to `POST /api/shopify/checkout`. The service looks up the real
prices, names, SKUs and stock from Shopify's Storefront API, creates a session and returns the `checkout_url`. **Prices are
never taken from the browser.** Out-of-stock or unknown items are rejected with a message the shopper sees. The endpoint only
answers browsers on your store's origin (CORS), and is rate-limited per client (20 requests/minute).

Limits: Shopify's own checkout remains reachable at `/checkout` for anyone who types it; inventory is not decremented in
Shopify; the service must be on a public **https** address (`PUBLIC_URL`). Check Shopify's terms for third-party checkouts.
`SHOPIFY_API_BASE_URL` overrides the Storefront API host for local development against a fake Shopify.

## Card payments (through the client's processor)

Customers can pay by card on this checkout while the **client's own processor** takes the payment:

1. The customer types the card into the **processor's hosted fields** inside our checkout page (provider SDKs live in
   `frontend/checkout/card/`). The card number goes browser → processor only; our page and server only ever see a
   single-use **token**.
2. The checkout sends the order and token to the **client's charge API** (a signed `POST` with an `Idempotency-Key`), and
   the client's server charges it with their processor account and answers `succeeded` / `declined`.
3. `succeeded` creates the order as **paid** with the processor's charge id as its reference; a decline is shown to the
   customer, who can try another card.

Set it up in **Admin → Settings → Card payments**: pick the card-fields provider, enter the processor's *publishable* key and
the client's charge URL, give the client the **signing secret**, press **Save & test client API**, then add the **Credit card**
payment method. The wire contract is in **[docs/client-payment-api.md](docs/client-payment-api.md)** and a complete, tested
reference implementation of the client's endpoint is in [`examples/client_payment_api.py`](examples/client_payment_api.py).

Two ways to show the card step, chosen per client in the admin (both use the same charge URL and signing secret):

- **Client-hosted card form** (`embed`): the client's card form is shown in an iframe on our checkout and the customer never leaves
  the page. See **[docs/embedded-card-form.md](docs/embedded-card-form.md)**.
- **Redirect to the client's payment page** (`redirect`): the customer is sent to the client's hosted payment page and the client
  marks the order paid through our store API. See **[docs/redirect-payment.md](docs/redirect-payment.md)**.

What ships: the whole flow, the signed/idempotent client API contract, and a **test provider** (fake fields, fake token).
What is still needed for real payments: one small file in `frontend/checkout/card/` wrapping the client's processor's
hosted-fields SDK (Stripe Elements, Authorize.net Accept.js, NMI Collect.js …) — it depends on which processor the client uses.
**Raw card numbers are never accepted by this server.** If the processor doesn't know about this checkout domain,
payments from it can be flagged.

## Webhooks

Set the URL in Settings. Events: `order.created`, `order.paid` (also when you mark an order paid), `order.updated`.
Each delivery is a `POST` of `{ id, event, created, data: <order> }` with headers `X-Checkout-Event` and
`X-Checkout-Signature: sha256=<hex HMAC-SHA256 of the raw body, keyed with your signing secret>`:

```python
expected = "sha256=" + hmac.new(SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
ok = hmac.compare_digest(expected, request.headers["X-Checkout-Signature"])
```

Failed deliveries are retried after 30 s, 5 min and 30 min (4 attempts total). Every retry sends the **same body and
event `id`**, so de-duplicate on `id`. Retries are stored in the database, so they survive restarts.

## Admin

- **Pending** – awaiting payment. Manual-payment orders and redirect payments waiting for the client's confirmation land here. Click **Mark paid** (optionally with the
  transfer's confirmation #) once the money arrives: the order moves to **Paid** and becomes `processing`.
- **Paid**, **Failed / Cancelled** (cancelled, failed payments, refunds).
- **Revenue** – today / 7d / 30d / all-time, daily chart, average order, outstanding and refunded totals, by payment method.
- **Email** – SMTP setup, which emails to send, test send, delivery log with retry.
- **Visits** – page views, unique visitors, devices, referrers and the funnel (created → viewed → ordered).
- **Settings & API** – API key, store name/currency/shipping/tax, payment methods, allowed redirect domains, webhooks,
  and **Branding** (below).

### Matching the checkout page to your storefront

The checkout page is styled like a storefront (white, flat boxes, royal-blue actions, bold uppercase headings). In
**Settings → Branding** you can add your **logo image URL**, the **store website** the logo links to, up to 8
**header menu links** (HOME, SHOP, FAQ…) and an optional **checkout notice** shown in a highlighted box. The cart icon in
the header shows the item count and returns the customer to your cart. To change the colours, edit the variables at the top
of `frontend/checkout/checkout.css` (`--brand` is the blue).

Set your payment instructions in **Settings → Payment methods**; `{order}`, `{total}` and `{store}` in the
instructions are filled in per order and included in the confirmation email.

## Project layout

```
app/
  main.py            application factory: lifespan, middleware, error handlers, static pages
  config.py          environment settings (pydantic-settings)
  database.py        engine + session management
  security.py        API-key / admin-token auth, login throttling
  errors.py          domain exceptions -> {"error": ...} responses
  models/            SQLAlchemy ORM models (orders, sessions, visits, outbox, settings)
  schemas/           Pydantic request/response models (the API contract)
  repositories/      all SQL lives here
  services/          business rules: checkout, orders, payments, emails, webhooks, reports…
  api/               thin FastAPI routers (store API, public checkout API, admin API)
  workers/outbox.py  background worker that delivers queued emails and webhooks
frontend/            shared/ (design tokens, icons), admin/ and checkout/ (HTML + CSS + ES modules), demo/
migrations/          Alembic migrations
tests/               pytest suite (integration tests against real MySQL)
```

Layering: `api → services → repositories → models`. Services never commit; the request owns one transaction.

### Design notes

- **Orders are normalised** (`orders`, `order_items`, `order_events`); order numbers come from MySQL `AUTO_INCREMENT`
  starting at 1001, so they are unique under any concurrency.
- **One order per checkout session** is enforced twice: a row lock on the session and a unique key on `orders.session_id`.
  Double-clicks and retries return the existing order.
- **Transactional outbox:** emails and webhooks are written to the database in the same transaction as the order change,
  then delivered by a worker (`SELECT … FOR UPDATE SKIP LOCKED` with a lease). Nothing is lost on a crash, and several
  instances can run workers safely.
- **Admin tokens are stateless** (signed, expiring), so restarts and multiple instances don't sign admins out.
- **Payments:** only an offline method (bank transfer), the redirect card flow and a *test* gateway are included, and no card data is
  collected. To take cards, add a gateway class in `app/services/payments.py` (verify the payment server-side and return
  `paid`).

## Development

```bash
# tests need a MySQL; they create and wipe their own database
docker run -d --name checkout-test-mysql -e MYSQL_ROOT_PASSWORD=testpw -p 3307:3306 mysql:8.4
TEST_DATABASE_URL=mysql+pymysql://root:testpw@127.0.0.1:3307/checkout_pytest pytest

ruff check . && ruff format .                                  # lint / format

alembic revision --autogenerate -m "describe change"           # after changing a model
alembic upgrade head                                           # (also runs automatically on startup)
```

A test fails if the models and migrations drift apart.

## Before going live

- Serve behind HTTPS and set `PUBLIC_URL` (and `TRUST_PROXY=true` behind a reverse proxy).
- Set a strong `ADMIN_PASSWORD`, and set **Allowed redirect domains** to your store's domain.
- Use a dedicated MySQL user (not root) and schedule database backups — MySQL now holds all your data.
- Settings (store API keys in `stores`, SMTP password in `settings`) are stored unencrypted — restrict database access.
- Login throttling is per process; with several instances put rate limiting at the proxy as well.
- Currencies are assumed to have two decimal places.
