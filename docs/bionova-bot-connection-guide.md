# Connecting your bots to the dashboard: Ads Data and All available sites

This guide explains how to feed the two new dashboard pages from your own bots.

- **Ads Data** has three sections: Canva, Excel and Credit Card Info.
- **All available sites** has five sections: Live Sites (included), Live GMB Profiles, Live Trustpilot Profiles, SEO per City and Reddit per City (all add-ons).

Your bots run on your side. They never connect to the dashboard itself. They only send messages to a private
API with a secret key, and **you decide what the customer sees**.

---

## 1. How it works

```
 your Grok bot ──(secret key)──▶  private API  ──▶  stored as hidden/draft
                                                          │
                                  you publish  ◀──────────┘
                                       │
                                       ▼
                            customer sees it in the dashboard
```

1. Your bot sends content for a section (a PUT request).
2. The content is **stored but not shown**. A brand-new section starts hidden.
3. You publish it (a PATCH request). Now the customer sees it.
4. Later updates from the bot **never replace what is showing**. They wait as a draft until you publish them.

> **The guarantee.** Nothing your bot sends ever goes live by itself, not even if it sends `"visible": true`. And if
> something is already published, sending an update never takes it down: the new content waits as a draft until you
> publish it.

Everything is versioned, so any change can be undone.

### What the customer sees

| State of a section | What the customer sees |
| --- | --- |
| Nothing published on the whole page | One "Coming soon" banner listing every section by name |
| At least one section published | Cards for the published sections, and a dashed "Coming soon" card for each one not yet published |
| A published section has a newer draft waiting | The current published content, unchanged |

Hidden content, drafts and deleted content are never shown to the customer.

---

## 2. What you need

| Item | Value |
| --- | --- |
| API address | `https://bionovaportal.com` |
| Ads Data key | sent to you separately, private. Opens **only** the Ads Data panel |
| All available sites key | sent to you separately, private. Opens **only** the sites panel |

The two keys are different, so you can run one bot per page, and a leak of one doesn't expose the other.

Every request carries the key in a header:

```
Authorization: Bearer YOUR_KEY
```

**Treat the keys like passwords.** Keep them in your bot's secret settings, never in code that is shared or
published. Whoever holds a key can push to, publish and delete that panel's content. If a key is ever exposed, ask us
to replace it (takes one minute).

### Panel and section names used in the API

| Page | Panel name | Section | Section name in the API |
| --- | --- | --- | --- |
| Ads Data | `ads` | Canva | `canva` |
| | | Excel | `excel` |
| | | Credit Card Info | `card_info` |
| All available sites | `sites` | Live Sites (included) | `live_sites` |
| | | Live GMB Profiles (add-on) | `gmb` |
| | | Live Trustpilot Profiles (add-on) | `trustpilot` |
| | | SEO per City (add-on) | `seo_city` |
| | | Reddit per City (add-on) | `reddit_city` |

---

## 3. Quick start (5 minutes)

These examples push content to Canva, look at it, then publish it.

**Step 1: push content (stored hidden)**

```bash
curl -X PUT https://bionovaportal.com/api/panels/ads/canva \
  -H "Authorization: Bearer YOUR_ADS_KEY" \
  -H "Content-Type: application/json" \
  -d '{"content": {
        "headline": "ROAS up 18% this week",
        "metrics": [{"label": "ROAS", "value": "4.2x", "trend": "+18%"}]
      }}'
```

The reply shows `"status": "hidden"`. The customer sees nothing yet.

**Step 2: look at what is stored** (this is how you review before publishing)

```bash
curl https://bionovaportal.com/api/panels/ads/canva -H "Authorization: Bearer YOUR_ADS_KEY"
```

**Step 3: publish it**

```bash
curl -X PATCH https://bionovaportal.com/api/panels/ads/canva \
  -H "Authorization: Bearer YOUR_ADS_KEY" \
  -H "Content-Type: application/json" \
  -d '{"visible": true}'
```

Now the customer sees the Canva card.

**The same thing in Python:**

```python
import requests

BASE = "https://bionovaportal.com"
HEADERS = {"Authorization": "Bearer YOUR_ADS_KEY"}

requests.put(f"{BASE}/api/panels/ads/canva", headers=HEADERS, timeout=30,
             json={"content": {"headline": "ROAS up 18% this week",
                               "metrics": [{"label": "ROAS", "value": "4.2x", "trend": "+18%"}]}}).raise_for_status()

# when you are ready for the customer to see it:
requests.patch(f"{BASE}/api/panels/ads/canva", headers=HEADERS, timeout=30,
               json={"visible": True}).raise_for_status()
```

On Windows PowerShell, use `curl.exe` (plain `curl` is a different command) or `Invoke-RestMethod`.

---

## 4. Everyday workflow

The normal rhythm for a bot:

1. **Push** the latest content to a section as often as you like (for example every 15 minutes).
   - Section not yet published: each push replaces the stored content.
   - Section published: each push becomes a draft, and the customer keeps seeing the published version.
2. **Review.** Read the section (`GET`). It shows `content` (what the customer sees), `pending` (the draft) and `status`.
3. **Publish** when you are happy (`PATCH {"visible": true}`). A waiting draft replaces the published content.
4. **Hide** a section any time (`PATCH {"visible": false}`). It disappears for the customer, and any draft stays safe.

Publishing is always your call, never your bot's, unless you choose to have your bot publish too (it can, with the same key).

### Scenarios

| What happens | Result |
| --- | --- |
| First push to a section | Stored **hidden** |
| Push while the section is hidden | Stored content is replaced |
| Push while the section is published | New content waits as a **draft**; customer still sees the old |
| Publish while a draft is waiting | Draft goes live, draft slot is emptied |
| Publish with no draft waiting | Nothing changes |
| Hide a published section | Customer stops seeing it; any draft stays |
| Delete a section | Hidden at once, can be restored for 30 days, and any draft is discarded |
| Restore an old version | Comes back **hidden** (never goes live by itself), any draft is discarded |
| Push to a deleted section | Stored **hidden** (never comes back live by itself) |

---

## 5. Request reference

All addresses start with `https://bionovaportal.com/api/panels/{panel}`.

| Request | What it does |
| --- | --- |
| `GET /{panel}` | All sections of the panel with what is stored, drafts included |
| `GET /{panel}/{section}` | One section: `content`, `pending`, `visible`, `status` |
| `PUT /{panel}/{section}` | Push content (see rules above). Body: `{"content": {...}}` |
| `PATCH /{panel}/{section}` | Publish `{"visible": true}` or hide `{"visible": false}` |
| `DELETE /{panel}/{section}` | Delete (hidden at once, restorable for 30 days) |
| `GET /{panel}/{section}/versions` | List of earlier versions (numbers, action, date; no content) |
| `GET /{panel}/{section}/versions/{n}` | The full content of version `n` |
| `POST /{panel}/{section}/restore` | Bring back version `n`. Body: `{"version": n}` |
| `GET /{panel}/log` | Your key's recent activity (last 100 calls) |

### What a section looks like when you read it

```json
{
  "id": "canva",
  "title": "Canva",
  "status": "live",
  "visible": true,
  "content": { "headline": "Test" },
  "pending": { "headline": "Changed" },
  "deleted": false,
  "updated_at": "2026-11-18T13:49:03Z"
}
```

`status` is `live` (customer sees `content`), `hidden` (stored, not shown) or `coming_soon` (nothing stored).
After a push, the reply also contains `version`: the number of the snapshot taken of what was there before (empty for a brand-new section).

---

## 6. What you can send

The body of a push is `{"content": { ... }}`. Every part inside `content` is optional, and you can combine them in
one section. They appear in this order on the card.

| Part | What it is | Fields |
| --- | --- | --- |
| `headline` | One bold line | text, up to 300 characters |
| `summary` | A short paragraph | text, up to 2000 characters |
| `metrics` | Number tiles (up to 24) | `label` and `value` required. Optional `trend` and `hint` |
| `cards` | Credit cards (up to 50). **Credit Card Info only** | `label` and `last4` required. Optional `brand`, `note`, `spend`, `limit`, `currency`, `status` |
| `sites` | A table of sites (up to 200). **Live Sites only** | `name` required. Optional `url`, `status`, `uptime_pct`, `response_ms`, `last_checked_at` |
| `entries` | A list of items (up to 200) | `title` required. Optional `subtitle`, `city`, `url`, `image_url`, `status`, `rating`, `value`, `note`, `updated_at` |
| `table` | A free-form table | `columns` (up to 12 names) and `rows` (up to 500; each row has one cell per column) |

### Rules for values

- **Numbers or text:** `value`, `trend` and table cells accept both (`4.2`, `"4.2x"`). They are shown as text.
- **Trends:** a trend starting with `-` shows red; anything else shows green (`"+18%"`).
- **Statuses** are free text, and some get a colour:
  - green: `up`, `live`, `active`, `ok`, `good`, `online`, `verified`, `paid`, `published`
  - red: `down`, `offline`, `error`, `failed`, `inactive`, `suspended`, `blocked`
  - amber: `warn`, `degraded`, `slow`, `pending`, `partial`, `review`
  - anything else shows grey.
- **Web addresses** (`url`, `image_url`) must start with `http://` or `https://`.
- **Dates** use the international format: `2026-11-18T09:30:00Z`.
- **`rating`** is 0 to 5. **`uptime_pct`** is 0 to 100. **`response_ms`**, **`spend`** and **`limit`** cannot be negative.
- **`currency`** is a 3-letter code (`USD`, `CAD`). With it, `spend` and `limit` are shown as money.
- **`last4`** is exactly four digits, written as text (`"0042"`, not `42`).
- A message can be up to **256 KB**.
- **Unknown fields are refused**, so a typo shows up as an error instead of silently vanishing.

### Examples for every section

**Canva** (`ads/canva`)

```json
{"content": {
  "headline": "ROAS up 18% week over week",
  "summary": "Best performing creatives this week.",
  "metrics": [
    {"label": "ROAS", "value": "4.2x", "trend": "+18%", "hint": "vs last week"},
    {"label": "Ad spend", "value": "$12,480", "trend": "-3%"}
  ],
  "entries": [
    {"title": "Spring promo carousel", "subtitle": "Meta", "image_url": "https://example.com/a.png", "value": "5.1x", "status": "live"}
  ]
}}
```

**Excel** (`ads/excel`)

```json
{"content": {
  "headline": "Weekly ad performance",
  "table": {
    "columns": ["Campaign", "Spend", "Revenue", "ROAS"],
    "rows": [["Spring promo", "$4,200", "$21,420", "5.1x"], ["Retargeting", "$3,100", "$10,540", "3.4x"]]
  }
}}
```

**Credit Card Info** (`ads/card_info`): only the last 4 digits

```json
{"content": {
  "summary": "Ad spend per card this month.",
  "cards": [
    {"label": "Marketing Visa", "brand": "Visa", "last4": "4242", "spend": 8200.50, "limit": 15000, "currency": "USD", "status": "active"},
    {"label": "Backup Mastercard", "brand": "Mastercard", "last4": "4444", "spend": 4279.50, "limit": 10000, "currency": "USD", "note": "Used for Google Ads"}
  ]
}}
```

**Live Sites** (`sites/live_sites`)

```json
{"content": {
  "headline": "3 of 4 sites up",
  "metrics": [{"label": "Average uptime", "value": "99.96%"}, {"label": "Average response", "value": "182 ms"}],
  "sites": [
    {"name": "Toronto Plumbing", "url": "https://toronto.example", "status": "up", "uptime_pct": 99.99, "response_ms": 140, "last_checked_at": "2026-11-18T09:30:00Z"},
    {"name": "Ottawa Plumbing", "url": "https://ottawa.example", "status": "down", "uptime_pct": 97.1, "response_ms": 2400, "last_checked_at": "2026-11-18T09:30:00Z"}
  ]
}}
```

**Live GMB Profiles** (`sites/gmb`)

```json
{"content": {
  "entries": [
    {"title": "Toronto Plumbing", "city": "Toronto", "url": "https://maps.google.com/?cid=123", "status": "verified", "rating": 4.8, "value": "132 reviews"},
    {"title": "Ottawa Plumbing", "city": "Ottawa", "status": "pending", "note": "Verification postcard sent"}
  ]
}}
```

**Live Trustpilot Profiles** (`sites/trustpilot`)

```json
{"content": {
  "entries": [
    {"title": "Toronto Plumbing", "city": "Toronto", "url": "https://trustpilot.com/review/example", "rating": 4.6, "value": "212 reviews", "updated_at": "2026-11-18T09:00:00Z"}
  ]
}}
```

**SEO per City** (`sites/seo_city`)

```json
{"content": {
  "table": {"columns": ["City", "Keyword", "Position"], "rows": [["Toronto", "emergency plumber", 3], ["Ottawa", "drain cleaning", 7]]}
}}
```

**Reddit per City** (`sites/reddit_city`)

```json
{"content": {
  "entries": [
    {"title": "r/toronto: best plumber thread", "city": "Toronto", "url": "https://reddit.com/r/toronto/comments/abc", "value": "48 upvotes", "status": "active"}
  ]
}}
```

### Current limits to know about

- **Images are linked, not uploaded.** The `image_url` must be a public address your bot hosts somewhere (the dashboard
  stores no image files). Images show as **small thumbnails** next to a list item, not as large pictures. If you need
  large screenshots shown full-size, tell us and we will add it.
- **A card shows what you send it.** The dashboard does not calculate or chart anything. Your bot decides the numbers.

---

## 7. History, undo and delete

Every change takes a snapshot of what was there before, so nothing is lost by accident.

- **See the history:** `GET /{panel}/{section}/versions` lists versions (1, 2, 3…). `GET …/versions/2` shows the full
  content of version 2, exactly as it was before the change that created version 3.
- **Undo:** `POST …/restore` with `{"version": 2}`. The content comes back **hidden** (it never goes live on its own), so
  review it and publish. Restoring is itself a change that can be undone.
- **Delete:** `DELETE` hides the section for the customer at once. It can be restored for **30 days**, after which it is
  removed for good.
- **Retention:** the 30 most recent versions of a section are always kept, plus everything from the last 90 days.

### Activity log

`GET /{panel}/log` shows the last 100 calls made with your key: what was done, to which section, when, and whether it
succeeded (`ok`) or was refused (`rejected`) with the reason. It shows **only your own key's** activity. Failed attempts
with a wrong key are not recorded.

---

## 8. Errors and what they mean

| Code | Meaning | What to do |
| --- | --- | --- |
| 200 | Done | |
| 400 | The message is wrong (a message in the reply says which field) | Fix the content and send again. Nothing was stored |
| 404 | **Not found, or not allowed** (see below) | Check the address, the key and the section name |
| 422 | The content contains what looks like a **full card number** | Send only the last 4 digits. Nothing was stored |
| 429 | Too many requests (over 300 a minute) | Slow down and retry |
| 5xx | A problem on our side | Retry in a minute. If it continues, tell us |

### About the 404

For security, **every kind of access failure looks identical**: a wrong or missing key, a panel or section name that
doesn't exist, a method that isn't allowed, or an address that isn't permitted all return the same plain
`404 Not Found`. This is deliberate, so nobody can probe the system. It means a 404 can hide a mistake of yours. Check, in order:

1. Is the **key** the right one for this panel? The Ads key does not open the sites panel and vice versa.
2. Is the key copied **exactly**, with no extra space or line break, and sent as `Authorization: Bearer <key>`?
3. Is the **panel** (`ads` or `sites`) and **section** name exactly as in the table in section 2?
4. Is the **method** right (`PUT` to push, `PATCH` to publish)?

### Card numbers are refused, everywhere

Every piece of text in anything you send is scanned for what looks like a complete card number (13 to 19 digits that
pass the standard card check). If one is found, the **whole message is refused** (422) and nothing is stored. This
applies to every section, not only Credit Card Info. In Credit Card Info, the `last4` field accepts exactly four digits.

---

## 9. Limits

| Limit | Value |
| --- | --- |
| Message size | 256 KB |
| Requests | 300 per minute per key and address |
| Metrics per section | 24 |
| Entries / sites per section | 200 |
| Cards per section | 50 |
| Table | 12 columns, 500 rows |
| Text | headline 300 characters, summary 2000, a table cell 300 |

---

## 10. Questions

**Can the customer see my bot's drafts or my history?** No. The customer sees only published content.

**Can I run several bots on one panel?** They would share the panel's key and their pushes replace each other, so use one
bot per panel, as planned: one for Ads Data, a different one for sites.

**Can a bot publish by itself?** Yes, if you let it send the `PATCH`. If you want a person to approve everything,
keep `PATCH` for yourself and let the bot only `PUT`.

**Does the content depend on the store?** No. The two pages are the same for every store connected to this checkout.

**A section was published by mistake. What now?** `PATCH {"visible": false}` hides it immediately.

**How do I get a new key?** Ask us. It takes one minute and the old key stops working at once.

**Is there a test mode?** Everything starts hidden, so pushing is safe: the customer sees nothing until you publish.
