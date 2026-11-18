# Content panels (Ads Data, Sites)

Two pages in the admin, **Ads Data** and **Sites**, are filled by an automated feed (a bot or a scheduled job) through a
private API. Each page is a fixed list of cards. A card nobody has published yet shows "Coming soon". The content is the
same for every store.

## The promise

> Nothing you send ever goes live by itself, not even if you send `"visible": true`. And if something is already
> published, sending an update never takes it down: your new content waits as a draft until someone explicitly
> publishes it.

Everything you send is versioned and can be undone.

## Setup

Set one key per panel in the environment (never in the database), then redeploy:

| Panel | Slug | Environment variable |
| --- | --- | --- |
| Ads Data | `ads` | `ADS_DATA_KEY` |
| Sites | `sites` | `SITES_KEY` |

A key opens its own panel only. A panel whose key is unset is switched off. `PANEL_ALLOWED_IPS` (comma-separated,
optional) limits which addresses may call the API.

Send the key as `Authorization: Bearer <key>`.

**Anything that fails authentication or routing answers with the same `404 Not Found` as a path that does not exist:**
a wrong or missing key, an unknown panel or section, a blocked address, or a method the route does not handle. Nothing
is logged for those calls. Calls are throttled to 300 per minute per panel and address.

## Sections

| Panel | Section id | Title |
| --- | --- | --- |
| `ads` | `canva` | Canva |
| `ads` | `excel` | Excel |
| `ads` | `card_info` | Credit Card Info |
| `sites` | `live_sites` | Live Sites (included) |
| `sites` | `gmb` | Live GMB Profiles (add-on) |
| `sites` | `trustpilot` | Live Trustpilot Profiles (add-on) |
| `sites` | `seo_city` | SEO per City (add-on) |
| `sites` | `reddit_city` | Reddit per City (add-on) |

## Endpoints

All under `/api/panels/{panel}`.

| Call | What it does |
| --- | --- |
| `GET /{panel}` | Every section with what is stored, drafts included |
| `GET /{panel}/log` | This key's own recent activity |
| `GET /{panel}/{section}` | One section: `content` (live), `pending` (draft), `visible`, `status` |
| `PUT /{panel}/{section}` | Push content. A new section is created hidden. A hidden one is replaced. A **live** one keeps showing as it is and the new content becomes `pending` |
| `PATCH /{panel}/{section}` | `{"visible": true}` publishes (promoting a waiting draft), `{"visible": false}` hides (a draft stays) |
| `DELETE /{panel}/{section}` | Soft delete (restorable for 30 days; discards a draft) |
| `GET /{panel}/{section}/versions` | Version numbers, actions and dates (no content) |
| `GET /{panel}/{section}/versions/{n}` | The content as it was before that change |
| `POST /{panel}/{section}/restore` | `{"version": n}`. Comes back hidden, discards a draft, and is itself undoable |

Keep the last 30 versions of each section, or everything from the last 90 days, whichever is more.

## What you can send

`PUT` body: `{"content": { ... }}`. Every part is optional and parts can be combined. Unknown fields are rejected.

| Field | Shape |
| --- | --- |
| `headline`, `summary` | text |
| `metrics[]` | `label`, `value`, optional `trend`, `hint` (stat tiles) |
| `entries[]` | `title`, optional `subtitle`, `city`, `url`, `image_url`, `status`, `rating` (0-5), `value`, `note`, `updated_at` |
| `sites[]` | `name`, optional `url`, `status`, `uptime_pct`, `response_ms`, `last_checked_at`. **Sites > Live Sites only** |
| `cards[]` | `label`, `last4` (exactly 4 digits), optional `brand`, `note`, `spend`, `limit`, `currency`, `status`. **Ads Data > Credit Card Info only** |
| `table` | `columns` (list of names) and `rows` (list of rows, each as long as `columns`) |

URLs must start with `http://` or `https://`. A body can be 256 KB at most.

**Card numbers are refused.** Every string in a payload, in any section, is scanned for a full card number (13-19
digits that pass the Luhn check). If one is found the push is rejected with `422` and nothing is stored. Send only the last 4 digits.

## Example

```bash
curl -X PUT https://YOUR-HOST/api/panels/sites/live_sites \
  -H "Authorization: Bearer $SITES_KEY" -H "Content-Type: application/json" \
  -d '{"content": {"headline": "All sites up",
        "sites": [{"name": "Toronto", "url": "https://toronto.example", "status": "up", "uptime_pct": 99.98}]}}'
# publish it, once someone has looked at it
curl -X PATCH https://YOUR-HOST/api/panels/sites/live_sites \
  -H "Authorization: Bearer $SITES_KEY" -H "Content-Type: application/json" -d '{"visible": true}'
```

Note that the key's `PATCH` is what publishes. Whoever holds the key can publish, so share it only with the people or
jobs allowed to.
