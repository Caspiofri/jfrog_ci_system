# API contract v1: for review, nothing implemented

Oct 31, 2026 · for Ofri's review · repo at `main` f4ee625

**Base:** the prototype's 18-dataset contract (`docs/specs/dashboard_explained.md` §5), trimmed to the D35 build list: items, competitors, h2h, activity, funnel, silent, eval, intensity, deals and insights. Pressure and gaps are included only if the capability-baseline step lands. One endpoint group per screen (D21).

**Decisions it applies:** D31 (Found-late badge, Brief windows since the previous Brief, card counts by discovery time), D32 (untrusted text), D33 (0.82 linking only), D34 (three autonomy levels, Trust this source, the demo field allowlist) and D35 (only charts with pipeline data).

**What it replaces:** plan section 2 (`2026-10-31-events-freshness-api.md`) in four places:
- the confidence threshold becomes the D34 levels
- the Trust-this-source action is added
- the responses use the prototype's dataset names, so the UI swap is 1:1
- article text never leaves the API

Plan 2.1's conventions are unchanged: `/api/v1`, list envelope, errors, ETag, `meta`, demo mode.

## 0. Field status markers

Every field in this document carries one of these markers.

| Mark | Meaning |
|---|---|
| ✅ | **Stored today** in `data/ci/ci.sqlite`, `data/ci/changes.sqlite` or `output/` |
| 🔧 | **A query over stored data.** It needs API code but no new pipeline step |
| ❌ | **Not produced by the pipeline yet.** It needs new pipeline code or new storage; the step is named |
| ⬚ | **Baseline-only.** It exists only if the capability-baseline step lands (D29, plan §3) |

**What the store holds today:**
- runs
- kept items with `discovered_at`
- sightings
- classifications and rankings, each with its fingerprint
- rejections (D32)
- skips (test split)
- cells (h2h)
- the run reports, coverage reports and eval reports

**What it doesn't hold:**
- dropped items: dedupe drops live only in `output/runs/*.dropped.jsonl`
- events
- routing status
- analyst actions
- Briefs
- insights

## 1. Conventions added to plan 2.1

- **Score.** `score` is an `int 1..5`, or `null` with `noise: true` (rubric v2, D29). The prototype's `importance: 0` for noise maps to this pair. `urgency` 🔧 is derived from the score as in the prototype: 5 Act now, 4 This week, 3 Monitor, 1–2 FYI.
- **Untrusted text (D32).**
  - `title`, `excerpt`, `reason` and `why_it_matters` are plain text from or about sites we don't control. The API never returns HTML; the UI escapes everything.
  - The API never returns full article text. `excerpt` is at most 280 characters, so the live API and the demo snapshot have the same shape.
- **Demo snapshot (D34).**
  - The snapshot keeps only the allowlisted fields: title, URL, dates, source, competitor, category, score, status, reason, our summary (`why_it_matters`) and `excerpt`.
  - Every field below that isn't on the list is marked **(live only)**, and the demo API returns it as `null`.
  - The demo API is the same code and the same response models.
- **Cross-site writes (CSRF).** The API binds 127.0.0.1 and has no login, so every POST, PUT, PATCH and DELETE is refused with `403 csrf_refused` when the browser marks it cross-site: `Sec-Fetch-Site` other than `same-origin` or `none`, or, without that header, an `Origin` that is neither a loopback host nor the request's own host. The UI's same-origin calls through its `/api/v1` proxy and requests without browser headers (curl, scripts) are unaffected; extra origins go in `CI_ALLOWED_ORIGINS`. Reads are never blocked (`ci/csrf.py`).
- **Times.** UTC `…Z`. `date` is an Israel date (`YYYY-MM-DD`). `published_at` is the publication time; `discovered_at` is when our first run saw the item.
- **Unit of a row.** In v1 a row is an **item** (`item_id`), not an event. Events (plan 1.4–1.7) aren't built: dedupe drops point to the kept item through `duplicate_of`, and that's all.
  - `event_id` is in the contract as ❌ and `null` until events land.
  - Everything that says "event" in plan section 2 reads "item" here.
  - Under D33 the firewall changelog and its news coverage are two rows in either model.

## 2. Shared objects

### `Item` (from the prototype's `items` dataset)

Used by the Brief, the Competitors profile, Review and Log.

| Field | Type | Mark | Source / note |
|---|---|---|---|
| `item_id` | str (16 hex) | ✅ | `items.item_id` (prototype `id`) |
| `title` | str | ✅ | `items.title` |
| `url` | str | ✅ | `items.url` |
| `excerpt` | str ≤ 280 | 🔧 | the first 280 characters of the stored text (the teaser when the page is junk) |
| `source` | `google_news`\|`vendor_feed`\|`github_releases`\|`hackernews` | ✅ | `items.source` |
| `publisher` | str | ✅ | `items.raw.publisher`, else the URL host |
| `publisher_host` | str | 🔧 | the URL host; Trust this source acts on it |
| `competitor` | key | ✅ | `classifications.competitor`. The prefilled value is only a fallback for test-split items, marked by `classified: false` |
| `classified` | bool | 🔧 | false for test-split items (skips) until after the test eval |
| `category` | D11 label \| null | ✅ | `classifications.category` |
| `noise` | bool | ✅ | `classifications.noise` |
| `score` | int 1..5 \| null | ✅ | `rankings.score` |
| `urgency` | `act_now`\|`this_week`\|`monitor`\|`fyi`\|null | 🔧 | derived from `score` |
| `confidence` | float | ✅ | `classifications.confidence` (shown, not used for routing under D34) |
| `mentions_jfrog` | bool | ✅ | `classifications.mentions_jfrog` |
| `reason` | str | ✅ | `rankings.reason` (the score's reason) |
| `why_it_matters` | str ≤ 160 | ✅ | `rankings.why_it_matters` ("our summary") |
| `published_at` | …Z \| null | ✅ | `items.published_at` |
| `date_precision` | `time`\|`day` | ✅ | `items.raw.date_precision` |
| `discovered_at` | …Z | ✅ | `items.discovered_at` (only moves earlier) |
| `discovery_lag_hours` | float \| null | 🔧 | `discovered_at − published_at` |
| `badge` | `new`\|`late`\|null | 🔧 / ❌ | **D31.** In a Brief context, computed live from the Brief window (§3.1). Freezing it per Brief needs ❌ a `brief_items` table. `follow_up` needs ❌ events |
| `status` | `auto_published`\|`awaiting_review`\|`approved`\|`dismissed`\|`flagged`\|`dropped` | ❌ | ❌ `ci/route.py` (a pure function of hold reasons + level, §5) + ❌ `item_state` for analyst decisions. **Until those land, every item that isn't noise is `awaiting_review` or `auto_published`, computed by the 🔧 routing query** |
| `hold_reasons` | [`HoldReason`] | 🔧 / ❌ | §5. Computed from stored fields; `changed_cell` comes from changes.sqlite |
| `stage` | `url_dedupe`\|`embedding_dedupe`\|`test_skip`\|`classify`\|`rank`\|`validate`\|`route`\|`analyst` | 🔧 / ❌ | where the item stopped. Dropped items need ❌ dropped rows in the store (today they're only in `.dropped.jsonl`); `analyst` needs ❌ `item_state` |
| `stage_reason` | str | 🔧 / ❌ | the dedupe reason, the skip reason, the rejection reason (D32) or the routing reasons |
| `fingerprint`, `run_id` | str | ✅ | `classifications` **(live only)** |
| `event_id` | str \| null | ❌ | events not built (D33 keeps 0.82; plan 1.4–1.7) |
| `jfrog_product` | `Curation`\|`Xray`\|`Artifactory`\|`AI/MCP`\|`none` | ⬚ | needs the classifier axis + a mapping table |
| `impact_type` | `existing_threat`\|`gap`\|`market`\|`pricing`\|`messaging` | ⬚ | baseline step |
| `gap` | str \| null | ⬚ | baseline step |

### `HoldReason`

```json
{"code": "unvetted_source", "detail": "publisher host gbhackers.com is not on the vetted list", "held_at": ["strict"]}
```

`held_at` lists the levels that hold the item for this reason; see the table in §5.

## 3. Endpoints by screen (D21)

| Group | Method & path | Datasets it serves |
|---|---|---|
| shared | `GET /api/v1/meta` | competitors, categories, axes, levels, reason codes, the latest Brief date, the latest daily run |
| shared | `GET /api/v1/items/{item_id}` | the item drawer: `Item` + classification method, ranking adjustments, sightings, rejections, actions |
| **Brief** | `GET /api/v1/brief?date=` | `items` (the Brief window), `insights`, `intensity`, KPI counts; `pressure` ⬚ |
| Brief | `GET /api/v1/briefs?limit=&offset=` | past Briefs (day navigation) |
| Brief | `POST /api/v1/brief/{date}/insights/refresh` | **Refresh insights (D37):** regenerate after analyst approvals; the 06:00 version is kept |
| **Competitors** | `GET /api/v1/competitors?date=` | `competitors` (cards), `deals` |
| Competitors | `GET /api/v1/competitors/{key}?date=` | the profile: `h2h`, `activity`, latest `items`, `deals`; `gaps` ⬚ |
| **Review** | `GET /api/v1/review?level=&reason=&competitor=&limit=&offset=` | held `items` + held cell changes, counts by reason, counts per level |
| Review | `GET /api/v1/settings/autonomy-level`, `PUT …` | the current level + what each level holds |
| Review | `POST /api/v1/items/{id}/approve` · `/dismiss` · `PATCH /items/{id}` · `POST`/`DELETE /items/{id}/flag` | D16 actions (bodies and transitions as in plan 2.6) |
| Review | `POST /api/v1/changes/{id}/approve` · `/dismiss` · `PATCH /changes/{id}` | changed-cell review (plan 2.6) |
| Review | `POST /api/v1/sources/trust`, `DELETE /api/v1/sources/trust/{host}`, `GET /api/v1/sources?kind=` | **Trust this source (D34)** |
| **Log** | `GET /api/v1/log?…filters…` | `items` (every sighting, including dropped), counts by status and stage |
| **Health** | `GET /api/v1/health?run_id=` | `funnel`, `silent`, `eval` (+ coverage), change detection |
| Health | `GET /api/v1/runs?limit=&offset=` | run list |

**Roadmap tab (D35):** static screenshots shipped with the UI, so no API. That covers strength, convergence, emerging, topics, reactions, team chips, Market view and the battlefield matrix (the matrix needs `jfrog_product` ⬚).

### 3.1 Brief: `GET /api/v1/brief?date=2026-11-01`

**Window (D31).** The Brief for date D covers everything discovered since the previous Brief, anchored on the daily run, not a fixed 24 hours:
- `anchor` is the `started_at` of D's daily run 🔧. That's the 06:00 `kind=daily` run in `runs`, or the first successful daily run on D.
- `prev_anchor` is the previous Brief's anchor 🔧.
- An item is in Brief D when `prev_anchor < discovered_at ≤ anchor`. Its current status must be published.
- **badge:** `new` when `published_at > anchor − 24h` (or the publication date is unknown); otherwise `late`, shown as "Found late" with the publication date. Day precision is shown as "date only".

```json
{
  "date": "2026-11-01",
  "status": "ok",                                     // ok | partial (insights failed) | missing (no daily run) 🔧
  "window": {"prev_anchor": "2026-10-31T13:45:00Z",   // 🔧 runs (the first Brief: anchor − 24h)
             "anchor": "2026-11-01T04:00:00Z",
             "anchor_run_id": "20261101T0400Z-xxxxxx",
             "hours": 14.25,                          // > 24 after a missed day
             "tz": "Asia/Jerusalem"},
  "counts": {"items": 12, "new": 9, "found_late": 3,   // 🔧
             "awaiting_review": 4,                    // 🔧 at the current level
             "by_urgency": {"act_now": 0, "this_week": 1, "monitor": 6, "fyi": 5}},
  "kpis": [                                           // 🔧 the prototype's 4 tiles, each with the previous Brief
    {"key": "items", "value": 12, "prev": 14},
    {"key": "important", "value": 1, "prev": 2},     // score >= 4
    {"key": "found_late", "value": 3, "prev": 1},
    {"key": "mentions_jfrog", "value": 0, "prev": 1}],
  "insights": {                                       // ✅ generator built (ci.insights, 1367544); not in the daily run yet
    "status": "ok",                                   // ok | partial (< 3) | none (no candidate group) | failed
    "generated_at": "…Z", "trigger": "daily",         // daily | refresh
    "level": "strict", "fingerprint": "…", "model": "gemini-3.6-flash",
    "window": {"from": "2026-10-16", "to": "2026-10-30", "days": 14, "items": 0, "stories": 0},  // example shape; counts not measured yet
    "rejected": 1,                                    // count; the reasons are on Health
    "items": [{"insight_id": "ins_2026-10-30_1", "pattern": "competitor_momentum",
               "title": "…", "summary": "…", "why_it_matters": "…",
               "claims": [{"text": "…", "item_ids": ["…"], "quote": "…", "quote_item_id": "…"}],
               "item_ids": ["…"], "story_ids": ["…"], "max_score": 5,
               "axis": null, "jfrog_cell": null,       // ⬚ until the capability baseline lands
               "baseline_note": "No JFrog capability baseline yet: this insight makes no gap claim."}]},
  "intensity": {"days": 14, "series": [{"date": "2026-10-19", "score": 21, "items": 9}]},  // 🔧 §4.8
  "items": {"total": 12, "limit": 50, "offset": 0, "items": ["Item …"]}
}
```

- **Order:** score descending (noise never appears), then confidence, then the newest `published_at`, then `item_id`. The badge doesn't change the order (D31).
- **Today:** none of the Brief rows above exist yet. A Brief for any date is computed on the fly 🔧 from `runs` and `items`, and `briefs` lists the dates that have a daily run.
- **Freezing:** freezing a Brief's membership and badges needs ❌ `briefs` + `brief_items` (plan 1.6). Until then, a past Brief can change if an analyst acts later.

### 3.2 Competitors

**Counts by discovery time (D31).**
- `items_today` is the Brief window of D.
- `items_7d` counts items with `discovered_at` in `(anchor(D) − 7d, anchor(D)]`; `items_prev_7d` is the 7 days before that.
- Only published items count; held ones are reported as `pending_review`.
- The activity chart is drawn by `published_at` (the Israel date), so a late discovery sits on the day it happened. Each item shows its publication date.

`GET /api/v1/competitors?date=` returns the `competitors` dataset:

| Field | Mark | Note |
|---|---|---|
| `key`, `name`, `is_industry` | ✅ | `config/competitors.yaml` |
| `items_today`, `items_7d`, `items_prev_7d`, `trend` (`up`\|`down`\|`flat`, flat when \|Δ\| ≤ 1) | 🔧 | by `discovered_at`, published only |
| `threat` | 🔧 | max `score` of the published items in 7d; null when none |
| `pending_review`, `pending_max_score` | 🔧 | held items in 7d at the current level |
| `tracked_changes` | ✅ | changes.sqlite `changes` in 7d (null for Industry) |
| `head_to_head_changes` | 🔧 | cells with a change in 7d |
| `mentions_jfrog` | 🔧 | 7d |
| `category_mix` | 🔧 | `[{"category", "count"}]` (prototype: "Category:n;…") |
| `top_item` | 🔧 | `{item_id, title, score, badge}` |
| `summary` | ❌ | an AI "this week" summary (plan 2.5; insights step) |
| `deals` | 🔧 / ❌ | see §4.9 |

`GET /api/v1/competitors/{key}?date=` returns the profile: `h2h`, `activity`, `latest_items` (`Item` list, paginated), `deals`, `gaps` ⬚ and `summary` ❌.

### 3.3 Review: hold reasons and the three levels (D34)

```json
GET /api/v1/review?level=strict
{
  "level": "strict",                                  // the current level unless ?level= previews another one
  "levels": [                                         // 🔧 counted over the scope below, at each level
    {"level": "strict",   "held": 84, "published": 144, "n": 228},
    {"level": "balanced", "held": 28, "published": 200, "n": 228},
    {"level": "relaxed",  "held": 12, "published": 216, "n": 228}],
  "scope": {"kind": "run", "run_id": "20261030T1312Z-389e71"},  // default: the latest Brief; or ?date_from=&date_to=; non-noise items
  "counts_by_reason": {"unvetted_source": 79, "pricing": 3, "m_and_a": 4, "mentions_jfrog": 5,
                       "model_failure": 0, "invalid_output": 0, "changed_cell": 0},  // an item can count twice
  "total": 84, "limit": 50, "offset": 0,
  "items": [
    {"kind": "item", "item": "Item …", "held_since": "…Z",
     "hold_reasons": [{"code": "unvetted_source", "detail": "publisher host gbhackers.com is not on the vetted list",
                       "held_at": ["strict", "balanced"]}],   // balanced too, because score >= 4
     "trust_source": {"host": "gbhackers.com", "approved": 2, "dismissed": 0, "suggest": false}},  // ❌ counts
    {"kind": "change", "change_id": "…", "competitor": "snyk", "axis": "pricing_model",
     "old_value": "…", "new_value": "…", "hold_reasons": [{"code": "changed_cell", "held_at": ["strict", "balanced", "relaxed"]}]}
  ]
}
```

The `levels` numbers above are the measured ones from the 14-day import (n=228 non-noise items): Strict 84, Balanced 28, Relaxed 12. The response shape is the contract; the numbers are an example.

`PUT /api/v1/settings/autonomy-level`:
- Body: `{"level": "balanced"}`. It returns the same `levels` block and bumps `store_version`. ❌ It needs a `settings` table.
- Default `strict`.
- Items already decided by an analyst keep their decision.
- `GET` with `?preview=relaxed` changes nothing.

### 3.4 Trust this source (D34)

| Endpoint | Body | Effect | Mark |
|---|---|---|---|
| `POST /api/v1/sources/trust` | `{"host": "gbhackers.com", "from_item_id"?: str, "note"?: str}` | Adds the host to the vetted list **in the store**, not in the repo file. Items held only for `unvetted_source` from that host stop being held at once | ❌ a `trusted_sources` table (host, added_at, actor, note, from_item_id) |
| `DELETE /api/v1/sources/trust/{host}` | none | Removes a store-added host. Hosts from `config/vetted_sources.yaml` can't be removed here (409) | ❌ |
| `GET /api/v1/sources?kind=vetted\|unvetted\|suggested` | none | Vetted: the yaml list ✅ + trusted ❌. Unvetted hosts seen, with item counts 🔧. **Suggested:** hosts with ≥ N approvals and 0 dismissals (Q-C) | ❌ needs `analyst_actions` |

The response to `POST`:

```json
{"host": "gbhackers.com", "group": "trusted", "added_at": "…Z",
 "released": {"total": 3, "item_ids": ["…"]},          // no longer held at the current level
 "still_held": {"total": 1, "item_ids": ["…"]}}        // held for another reason too
```

- A host matches its subdomains, as in `ci.sources` ✅.
- Press wires and aggregators stay unvetted unless they are trusted this way (D34).
- The yaml stays the repo's reviewed list.

### 3.5 Log

`GET /api/v1/log?run_id=&date_from=&date_to=&competitor=&category=&status=&stage=&source=&q=&sort=&limit=&offset=`
- **Rows:** one row per sighting (item × run), with `status`, `stage` and `stage_reason`.
- **`dismiss_reason`** (added 1 Nov): on every row. For a dismissed item, the reason of its latest dismiss action (`wrong_competitor`, `wrong_category`, `not_relevant` or `duplicate`); `null` on every other row, dropped rows included. `reason` is unchanged (`dismissed` for an analyst-stage dismissed row).
- **Counts:** by status and by stage.
- **Layout:** as the prototype; Ofri liked it as is.
- **Gaps today:**
  - Dropped rows need ❌ the drops in the store. Today they come from `output/runs/*.dropped.jsonl` 🔧, a file read that is fine for v1.
  - `rejected` (D32) rows ✅ come from `rejections`.
  - `test_skip` rows ✅ come from `skips`.
  - `fired_rule` from the prototype isn't in v1.

### 3.6 Health

`GET /api/v1/health?run_id=` (defaults to the latest daily run):

| Block | Dataset | Mark | Note |
|---|---|---|---|
| `run` | – | ✅ | `runs` (status, fingerprint, model, llm_calls, errors) |
| `funnel` | `funnel` | ✅ / 🔧 | per source, from the daily funnel (collected, dup_url, dup_embedding, kept, new, test_skip, rules, llm, fallback, noise, scored, rejected). The prototype's `published` and `held_for_review` come from 🔧 routing |
| `silent` | `silent` | 🔧 | `source`, `last_item`, `hours_silent`, `status` (Healthy\|Silent). The plan 2.8 rule needs ≥ 7 daily runs of history; until then it reports `"insufficient_history": true` with the number of runs |
| `run_metrics` | – | ✅ | the selected run's metrics row, or null for a run before Oct 31 night; see §11 |
| `eval` | `eval` | ✅ | the newest eval report in `output/evals/` (`<timestamp>.json`; the `insights_*.json` beside them are not eval reports); see below |
| `test_eval` | – | ✅ | the D23 test-split eval; `"status": "none"` until it has run; see §11.3 |
| `coverage` | – | ✅ | `output/coverage/<run>.json` |
| `change_detection` | – | ✅ | `output/changes/<run>.report.json` |

**Eval block:**
- Every metric is `{"metric", "value", "n", "note"}`.
- Important-item metrics carry `"weak": true` and a note: *"few important labels (n = 3 at score 4–5 across 107 labels); the coverage check is the main evidence for not missing important events."*
- `funding_m_and_a` is reported as *"untested: 0 labels"*.
- `coverage` is shown next to it as counts with their n, e.g. important captured 3 of 3 (n=3), never as a rate.
- Until a live test-split eval exists, the block says `"split"` and `"live"` for what it shows. No eval is run for this.

## 4. Datasets: trimmed to D35, with the marks

| # | Dataset | Screen | Status | What's missing |
|---|---|---|---|---|
| 4.1 | `items` | all | ✅ / 🔧 / ❌ | see `Item`: `status` ❌ (route + item_state), `event_id` ❌, `jfrog_product` / `impact_type` / `gap` ⬚ |
| 4.2 | `competitors` | Competitors | 🔧 | `summary` ❌ |
| 4.3 | `h2h` | Competitors profile | ✅ | `changed` 🔧 (cell history); `gap` ⬚ |
| 4.4 | `activity` | Competitors profile | 🔧 | per competitor per day, by `published_at` |
| 4.5 | `funnel` | Health | ✅ | `published` / `held_for_review` 🔧 |
| 4.6 | `silent` | Health | 🔧 | history: the store has 2 runs (the 14-day import and 1 daily run); the plan 2.8 rule needs ≥ 7 daily runs |
| 4.7 | `eval` | Health | ✅ | the test eval not run yet (waits for Ofri's go) |
| 4.8 | `intensity` | Brief | 🔧 | per day the sum of `score` and the count of non-noise items, **by discovery day** (Brief windows), 14 days |
| 4.9 | `deals` | Competitors | 🔧 / ❌ | rows = items in `Funding/M&A/Partnerships`: `date`, `competitor`, `title`, `url` 🔧. `type` (Acquisition\|Funding\|Partnership), `actor` and `target` ❌ need an extraction step. **0 labeled, 4 stored items in the category (n=228)** |
| 4.10 | `insights` | Brief | ✅ / ❌ | generator built and tested offline (`ci.insights`, D37): stories at 0.82, ≥ 2 stories per insight, a verbatim quote per claim checked in code. ❌ Not in the daily run, and never run live, until Ofri's expected-insights file is saved |
| 4.11 | `pressure` | Brief | ⬚ | needs `jfrog_product` |
| 4.12 | `gaps` | Competitors | ⬚ | needs `gap` |

Dropped from the API under D35, to the Roadmap tab: `strength`, `convergence`, `topics`, `reactions`, `emerging`, `invest`, team chips and insight `audience` / `action`.

## 5. Hold reasons and levels (D34)

| Code | When | Strict | Balanced | Relaxed | Mark |
|---|---|---|---|---|---|
| `unvetted_source` | the host isn't vetted (yaml ✅ + trusted ❌) | held | held when score ≥ 4 | – | 🔧 |
| `pricing` | category `Pricing & Packaging` | held | held | held | 🔧 |
| `m_and_a` | category `Funding/M&A/Partnerships` (the whole category, as measured) | held | held | held | 🔧 |
| `mentions_jfrog` | `classifications.mentions_jfrog` | held | held | held | 🔧 |
| `changed_cell` | a changed head-to-head cell (D13) | held | held | held | ✅ changes.sqlite |
| `model_failure` | a classifier fallback or degraded ranking | held | held | held | 🔧 |
| `invalid_output` | a D32 rejection | held | held | held | ✅ `rejections` |
| `low_confidence` | classifier confidence < 0.8 (D36 Q-A) | held | held | – | 🔧 |
| `teaser_high_score`, `junk_extraction` | snippet-only or junk text with score ≥ 4 (D36 Q-B; 11 of 228 items) | held | held | – | 🔧 |

Noise never reaches the queue; it goes to the Log (D9).

## 6. Decisions (Ofri, Oct 31; PRD D36): the contract is approved

- **Q-A:** low confidence (below 0.8) is held at Strict and Balanced, not Relaxed. Model failures and D32 rejections are held at every level.
- **Q-B:** teaser-only (score ≥ 4) and junk-extraction (score ≥ 4) items are held at Strict and Balanced and published at Relaxed.
  - With these rules the 14-day import holds **87 / 31 / 12** of n=228 (it was 84 / 28 / 12 before Q-B).
  - Built as `ci/route.py` (commit `b8d1d56`) and pinned in `tests/ci/test_route.py`.
- **Q-C:** suggest trusting a host after 3+ approvals and 0 dismissals.
- **Q-D:** a simple "Deals and partnerships" block on the Competitors overview: Funding/M&A/Partnerships items as they are (title, competitor, date, source). Buyer, target and type extraction goes to the Roadmap tab.
- **Q-E:** intensity by discovery day. **Q-F:** the excerpt is at most 280 characters.
- **Build order:** routing and statuses first, then the insights generator (the core of the Brief, D15), then the API for Brief, Review and Log, then Competitors and Health.

### D37 (insights)

- Insights count stories, not items (0.82 rule, ≥ 2 stories per insight).
- Patterns:
  - `axis_convergence` groups by category until the baseline gives an axis, with no JFrog cell and no gap claim.
  - `shared_threat` groups Security items across competitors and Industry.
- Every claim carries a verbatim quote checked against the cited item's text. Any failed check rejects the whole insight.
- Only published items feed insights. **Refresh insights** regenerates after analyst approvals; every generation is stored and the latest is shown.
- **Window, my choice (not in D37):** by publication time, 7 days widened to 14 when there are under 15 stories. That fits the addendum's fixed eval windows (Oct 16–30, Oct 23–30); by discovery time, the import would be a single day.

## 6a. The questions as asked

- **Q-A, low confidence.** D34's Strict is "everything D9 always holds", and D9 lists low confidence, but D34's Relaxed list omits it and D34 drops the number. I propose not holding on confidence at any level. A real model failure is `model_failure` and is held at every level. Confidence stays a visible field.
- **Q-B, the two existing ranker rules.** "Snippet-only item scored ≥ 4" and "junk extraction" (11 of 228) send items to review today. I propose holding them at Strict and Balanced (a high score resting on a teaser needs a human) and not at Relaxed.
- **Q-C, the Trust suggestion threshold.** I propose ≥ 3 approvals and 0 dismissals from one host.
- **Q-D, deals placement.** In the prototype deals sat in the Market view, which D35 moves to the Roadmap tab, yet deals is on the build list. I propose a "Deals and partnerships" block on the Competitors overview, all competitors in one list. `type` / `actor` / `target` would show as "not extracted yet" until an extraction step exists.
- **Q-E, intensity by discovery or publication day.** I propose discovery day, so it matches the Brief windows and the card counts (D31). The activity chart stays by publication day.
- **Q-F, excerpt length.** 280 characters, in both the live and demo API.

## 7. Build order once approved (one commit each, offline tests)

1. `ci/route.py`: hold reasons and levels (§5) as a pure function, with tests, including the 84 / 28 / 12 counts on a fixture.
2. Store: `settings`, `trusted_sources`, `item_state`, `analyst_actions`; the drops moved into the store.
3. API read endpoints (meta, Brief computed live, Competitors, Review, Log, Health), with response models validated in tests.
4. Actions + level + Trust this source.
5. Next.js UI per D35.

Afterwards: freezing Briefs, insights (`ci.brief`) and the deals extraction, each its own step.

## 8. As built: Brief, Review and Log (commit c03e0de)

`python -m ci.api --port 8010` binds 127.0.0.1. Tests are in `tests/ci/test_api.py` (16, offline). Where the build differs from the text above:

- **A Brief can be anchored on an import run.** An import run counts as the anchor of its day, like a daily run. So the 14-day import is the Brief of 2026-10-30, and the first daily run (Oct 31 13:45Z) is the Brief of 2026-10-31, covering everything discovered since the import.
  - On that Brief of 2026-10-30, 131 of the 141 published items are "Found late", which is correct for a 14-day backfill.
- **The Review queue lists every undecided held item by default**, not only the latest Brief's. Held items accumulate until someone decides them. `date_from` / `date_to` and `competitor` narrow it, and the `levels` block counts the same scope.
- **New status `held_out`:** golden-set test-split items. They're stored with no prediction, appear only in the Log (stage `test_skip`), and can't be acted on. Edits to them return 409.
- **Not in this step:**
  - change actions (approve, dismiss, edit a changed cell) come with Competitors and h2h; changed cells are listed in Review read-only
  - no ETag/304 yet
  - no demo mode yet (the freeze is on Tue 3 Nov)
- **Refresh insights** returns `409 insights_disabled` until the store setting `insights_enabled` is `"true"` (D37).
- **The edit candidates file:** `PATCH /items/{id}` appends to `evals/analyst_labels.jsonl` (`source: "analyst"`). It never touches `golden_set.jsonl`.

## 9. As built: Competitors, Health and anchor_kind (commits 6e35f7f, 4131c4c, fd6e933)

- **`anchor_kind`** (approved by Ofri, requested in `frontend/BACKEND_REQUESTS.md`): `"import"` or `"daily"` on `/brief` → `window`, and on every `/briefs` row. The UI labels the backfill Brief and hides its "Found late" badges.
- **Competitors:**
  - **Cards:** `GET /competitors` returns the cards (published items, by discovery time) plus a `deals` block. Deals are all Funding/M&A/Partnerships items with their `status`; M&A is held at every level, so they show `awaiting_review` until approved.
  - **Profile:** `GET /competitors/{key}` returns the card, head-to-head, activity (30 days, by publication day), latest published items and deals.
  - **Head-to-head:** lists all 7 axes for every competitor beside JFrog. Each cell's `state` is `value`, `stale`, `not_stated` (`value: null`: what the page doesn't say is a gap in our knowledge, not a value) or `not_tracked`.
  - **Not built:** `summary` is `{"status": "not_built"}`.
- **Changed cells:**
  - `POST /changes/{id}/approve`, `POST /changes/{id}/dismiss {reason}` (restores the old value) and `PATCH /changes/{id} {value}`.
  - A decided or superseded change returns 409. Each decision is logged in `analyst_actions` (`target_kind: "change"`) and in the cell history.
  - Review lists only changes still awaiting review.
- **Health:**
  - `GET /health?run_id=` returns `run`, `funnel` (with published / held at the current level), `silent_sources` (`runs_so_far`, `label: "n runs so far"`), `eval` (cards with `n`, `weak`, `untested`), `coverage` and `change_detection`. `GET /runs` lists the runs.
  - **Marker rules:** weak = n < 10, or any important-item metric. Untested = n = 0.
  - **Coverage:** counts with n, never a rate, recomputed from `evals/coverage_events.yaml` on the newest coverage run and labeled as the dev list (D26).
- **Tracked pages** (config, commit 6e35f7f): 21 pages, up from 15.
  - JFrog's security_scanning cell now comes from https://jfrog.com/advanced-security/ (D31 Q9).
  - New pages: GitHub package_coverage and curation_gating, GitLab package_coverage and curation_gating, Snyk deployment.
  - Still untracked: Snyk curation_gating, AWS security_scanning and ai_mcp, Cloudsmith pricing_model, each with its reason in the config.
  - The "prices rendered client-side" note now goes on pricing cells only, and a stored leaked note is repaired on the next live run.
- **Extraction on Health** (requested by Ofri, commit after fd6e933): `extraction.run` and `extraction.all` each give `extracted`, `n`, `rate`, plus `by_source` and `by_publisher` rows (`key`, `extracted`, `n`, `rate`, `by_status` {full, partial, snippet, junk}). Extracted means full or partial page text; n is the items kept. Why a fetch failed (e.g. a Cloudflare 403) isn't stored yet.

## 10. D44: the Daily Brief information hierarchy (contract for the UI, 31 Oct; as built)

The Brief separates what is known (published items scored 3+), what is pending (held items, as counts only) and what can't be concluded yet (insight states, the text basis). Everything here is a query over stored data 🔧, with no LLM call.

**Names.** They follow `frontend/BACKEND_REQUESTS.md` #3, which the UI already uses. This section is the single source of truth for them.

**Additive:** no field is removed. The fields marked *deprecated* stay until the UI has switched, then go.

### 10.1 `GET /api/v1/brief?date=`: items scored 3+ only (#3h)

- `items` lists the window's **published** items (`auto_published`, `approved`, `flagged`) with `score >= brief_min_score`.
  - `brief_min_score` is `3`, set in `config/brief.yaml` (`min_score`). It's a config value, not code, and it isn't part of any fingerprint.
  - The response echoes it as `brief_min_score`.
- Below the threshold, per rubric v2's "Shown in" column: score 2 belongs to the competitor profile and score 1 to the timeline. The Brief never lists them; it only counts them (`summary.published_below`).
- The score is the effective one: the analyst's edit if there is one, else the model's.
- Filters (`competitor`, `category`, `badge`), order and paging are unchanged (§3.1).

### 10.2 `summary`: the Brief window's counts (#3a)

```json
"summary": {
  "brief_min_score": 3,
  "published": 3,          // published, score >= 3: exactly the item list before filters
  "published_high": 1,     // of those, score 4-5
  "published_below": 0,    // published, score 1-2 (competitor profile / timeline)
  "held": 11,              // awaiting review at the current level, discovered in this window
  "held_high": 3,          // of those, preliminary score 4-5
  "held_by_preliminary_score": {"5": 0, "4": 3, "3": 6, "<=2": 2, "unscored": 0, "noise": 0},
  "level": "strict"
}
```

- **One query.** `summary` comes from the same window query as `items`: classified items with `prev_anchor < discovered_at <= anchor`, each with its status at the current level. So `published == items.total` when no filter is set.
- **Preliminary score** is the model's score on a held item (no human has confirmed it). Every key of `held_by_preliminary_score` is always present, zeros included.
  - `"unscored"`: held items the ranker gave no score (a ranker failure holds them as model_failure). They are not counted as `"<=2"`, so an outage doesn't read as "nothing big pending". They are part of `held` but never of `held_high`.
  - `"noise"` is 0 under the current routing, because noise is never held (D9). The key stays so the shape is fixed.
- **Not counted:** dismissed items, and held-out test-split items.
- **The link to Review:** `held` equals `total` of `GET /review?brief=<date>` at the same level (§10.3).
- **`/briefs` rows** gain `published`, `published_high`, `held` and `held_high`. Their `items` field is deprecated.
- **Deprecated:** `counts` and `kpis` (the four KPI cards) and `intensity` (the chart leaves the Brief).
  - The operational counts (Found late, Mentions JFrog, deltas vs the previous Brief) move to Health later (#3g, not built).
  - Until then these fields keep their old meaning: they count every published item in the window, whatever its score.

### 10.3 Review: filter by the Brief window (#3b)

`GET /api/v1/review?brief=2026-10-31` lists only the held items discovered in that Brief's window: the Brief links to "the 11 from this window", not to the whole backlog.

```json
"scope": {"brief": "2026-10-31", "window": {"prev_anchor": "…Z", "anchor": "…Z"},
          "date_from": null, "date_to": null, "competitor": null},
"total": 11,             // after every filter
"backlog_total": 84,     // every undecided held item at this level, with no filter; for the "backlog" badge
```

- `brief` combines with `level`, `reason` and `competitor`. An unknown date returns `404 not_found`.
- With `brief` set, changed cells aren't listed: they belong to no Brief window. They're still in the unfiltered queue.
- `backlog_total` is always present, on the filtered and the unfiltered queue alike.

### 10.4 Insight states (#3e)

`insights.status` is now the state the UI shows:

| `insights.status` | When |
|---|---|
| `disabled` | the store setting `insights_enabled` isn't `"true"` (`enabled: false` too) |
| `refreshing` | a Refresh for this date is running (started under 10 minutes ago). A second Refresh meanwhile gets `409 refresh_running` |
| `failed` | the latest generation failed (model error or a malformed answer); the Brief still shows its items |
| `none_passed` | the generator ran but kept no insight: every proposed insight failed its checks (`rejected` > 0), or there was no candidate group (`rejected` 0) |
| `ok` | at least one insight passed (`insights.items`, 1–5) |
| `not_run` | enabled, but nothing was generated for this date (e.g. the 14-day import's Brief of 30 Oct). **Added: not in D44's list.** Without it the UI would have to call a Brief that never ran "none passed" |

- `insights.rejected` is a **count** (it used to leak the stored list of reasons).
- The reasons stay in the stored generation, for Health (D37).
- The generator's raw status (`ok | partial | none | failed`) moves to `insights.generator_status`.
- No internal decision IDs ("D37") appear in any field meant for the UI.
- **Cited items (D50).** Each insight in `insights.items` gains `cited_items`, one row per cited item in claim order:
  `{"item_id", "title", "score", "url", "status", "in_brief"}`. The generator reads every published item of its
  window, scores 1–2 included, so `in_brief: false` marks a cited item that isn't in the Brief's list; the UI opens
  it by `item_id` (the item drawer). Additive: `item_ids` is unchanged.
- **Failures and second runs.** A generation that raises is stored as `failed`, so the Brief says `failed`, not
  `not_run`. A second daily run on the same Israel day doesn't regenerate that Brief's insights (they keep its
  window). A Refresh whose generation raises answers `502 insights_failed` and keeps the earlier generation.

### 10.5 Item payload: the text basis (#3c, D39) and the lens (D42)

Every `Item` gains `text_basis`, and `lens` gains `why_it_matters`:

```json
"text_basis": {
  "status": "snippet",                 // full | partial | snippet | junk
  "source": "teaser",                  // feed | page | teaser
  "reason": "cloudflare_challenge",    // null when the article text was used
  "reason_detail": null,               // junk: the extraction checks that failed
  "label": "Headline and teaser only", // the basis in words
  "chars_used_for_scoring": 212        // characters of text the ranker read
},
"lens": {"axis": "ai_mcp", "capability_quote": "…", "relation": "improves_shared",
         "why_it_matters": "…", "why": "…"}
```

- **`status` and `label`:**

  | `status` | `label` |
  |---|---|
  | `full` | Full article |
  | `partial` | Partial article |
  | `snippet` | Headline and teaser only |
  | `junk` | Teaser only (the page text was not the article) |

- **`reason`:**
  - `null` for `full` and `partial`.
  - `not_article` for `junk`, with the failed checks in `reason_detail`.
  - For `snippet`, the stored fetch status: `cloudflare_challenge`, `http_<code>`, `timeout`, `empty`, `not_html`, `connection_error`, `skipped_unresolved` (a Google News link that couldn't be decoded), `shorter_than_teaser` or `failed`.
  - `not_recorded` for items stored before fetch statuses existed (31 Oct).
- **`chars_used_for_scoring`:** the length of the text the ranker read. That's the article text, or the teaser for junk pages, capped at the ranker's 2,500 characters. The classifier reads the first 1,500 of the same text.
- **`lens`** is `null` when no lens passed its quote check, or none was run. When present:
  - `axis` is `null` for `not_related`.
  - `capability_quote` is `null` for `not_related`, else the verbatim line from the capability sheet.
  - `why_it_matters` is the lens sentence. `why` is the same text, kept for the current UI and deprecated.
- **`lens_status`** (added 1 Nov): the status of the item's latest lens row, so the UI can tell why `lens` is `null`.

  | `lens_status` | Meaning | `lens` |
  |---|---|---|
  | `ok` | The lens ran and its quote check passed | the object above |
  | `rejected` | The lens ran but its answer broke a rule (e.g. the capability quote is not on the sheet, or no answer for this item) | `null` |
  | `failed` | The lens call for its batch failed (model or parse error) | `null` |
  | `null` | No lens row: the lens was not run on this item | `null` |

- The item's own `why_it_matters` (the ranker's summary) is unchanged.
- **Not built:**
  - `lens.source_url` / `source_label` (#3d). The sheet's Sources list isn't labelled by axis, and most lines hold several links, so choosing one per axis would be a guess. It needs the sheet to name a source per axis row.
  - `rubric` in `/meta` (#3f).

### 10.6 `published_at` is never in the future (D24)

- A source date later than the collection time is stored as the collection time: we know the item existed then, not when it will claim to be published.
  - The source's own date is kept as `published_at_source`.
  - The store enforces it too: no item's `published_at` is later than its `discovered_at`.
- **Item fields** (every `Item`, 🔧):

  | Field | Type | Meaning |
  |---|---|---|
  | `published_at_source` | …Z \| null | the date the source gave, when it was later than our collection; else null |
  | `scheduled_for` | …Z \| null | `published_at_source` while it is still after the request time; null once it has passed |

- **UI:** when `scheduled_for` is set, the date reads "scheduled for <date> per source" instead of the publication date. Once the date has passed, `scheduled_for` is null and the UI shows `published_at` as usual. It may still note the source's date from `published_at_source`.
- The case that found it: Snyk's changelog RSS listed "Kubernetes connector reaches end of life - 02-Nov-202" with `pubDate: Sun, 01 Nov 2026 05:00:00 GMT`, a scheduled entry already in the feed on 31 Oct. The title's date is the end-of-life date, not the publication date.

### 10.7 Names changed from the first D44 draft (31 Oct)

| First draft (Ofri's C1 list) | Adopted (frontend #3) |
|---|---|
| `summary.published_in_brief` | `summary.published` |
| `summary.published_in_brief_4plus` | `summary.published_high` |
| `summary.published_below_brief` | `summary.published_below` |
| `summary.held_total` | `summary.held` (+ new `held_high`) |
| `GET /review?brief_date=`, `scope.brief_date` | `?brief=`, `scope.brief` |
| top-level `insights_status` | `insights.status` (raw status → `insights.generator_status`) |
| `insights.rejected_count` | `insights.rejected` (a count) |
| `text_basis.failure_reason` / `failure_detail` | `text_basis.reason` / `reason_detail` |

## 11. Per-run metrics and the test-split eval (31 Oct night; as built)

### 11.1 The metrics row

Every daily or import run writes one row to the store's `run_metrics` table when it ends: ok, degraded or failed. Every count comes with its n.

| Field | Content |
|---|---|
| `run_id`, `kind`, `status`, `started_at`, `finished_at`, `model`, `llm_calls`, `error` | as in `runs`; `error` is set on a failed run |
| `fingerprints` | `{classify_rank, lens, insights}`: the eval fingerprint and the lens and insights prompt fingerprints |
| `items` | `collected`, `kept`, `new`, `test_skip`, `to_model`, `noise`, `non_noise` (this run's own rows); `recovered`: items an earlier failed run stored but never classified, classified by this run (D49); `published`, `held` (awaiting review) and `by_status` at the level when the run ended, out of `routed_n` = items classified in this run |
| `extraction` | `extracted` of `n` kept items, and `by_source`: `{source: {extracted, n, fetch: {fetch_status: count}}}` |
| `lens` | `status`, `n`, `ok`, `rejected`, `failed`; `quote_check: {passed, failed, n}` (n = items whose relation needs a quote); `relations` over the ok lenses, with `relations_n`; `rejected_reasons` |
| `insights` | `status`, `produced`, `rejected`, `rejected_reasons: [{title, reason}]`, `brief_date`, `error` |
| `validation` | D32: `outputs` and `items` rejected, `by_stage`, `reasons: [{item_id, stage, reason}]` |
| `steps` | in order: `[{step, status, seconds, llm_calls, errors?, item_ids?, reason?}]`. Steps are `collect` or `load_run`, then `store`, `classify`, `rank`, `validate`, `lens`, `insights`. `status` is one of `ok`, `degraded` (some items fell back; `item_ids` lists them), `failed` (where the run stopped) or `skipped` (`reason`) |

On a failed run, the blocks the run never reached are null, and the last step present is the one that failed.

A run that stops before it writes its own row (another run held the lock, the split file is missing, a bad config, a crash before the store opens) gets a failed row too (D48): `runs.status` failed, a `run_metrics` row whose only step is `lock` or `start`, and the report's `failed_stage`. A row the crashed process left `running` is closed as failed instead. The exit code and traceback stay in `output/logs/ci_daily.log`. Every row and report also carries `metadata` (D53: fingerprints, `sheet_sha`, models, call settings, `combined`, `commit`).

### 11.2 Endpoints

- `GET /api/v1/run-metrics?limit=&offset=`: the rows, newest run first, paged like `/runs`.
- `GET /api/v1/run-metrics/{run_id}`: one row; 404 `not_found` when the run has none.
- `GET /api/v1/health` adds `run_metrics` for the selected run (`?run_id=`), or null.
- `GET /api/v1/health` adds `liveness` (D48): `{state, latest_run_id, latest_status, hours_since_latest, stale_run_ids, stale_after_hours: 1, overdue_after_hours: 26}`. `state` is `overdue` when the latest daily run started more than 26 h ago (a run that never started leaves no row, so this is how it shows), otherwise the latest daily run's marker; `none` when no daily run exists.
- `GET /api/v1/runs` rows add `marker`: `ok | degraded | failed | running | stale`. `stale` is a row still `running` more than 1 h after it started processing (killed or hung).
- The API's log is also appended to `output/logs/ci_api.log` (no rotation).
- **`/health` in demo mode (D83):** `eval`, `test_eval`, `coverage` and `change_detection` come only from saved summaries in the snapshot (`demo/snapshot/health/<block>.json`, written by `python -m ci.health_summary`); nothing is read from `output/` or recomputed. Each block keeps its live shape and adds `measured_on` (live too). A block with no file is `{"status": "not_in_snapshot", "note": "<block>: not included in this snapshot", "measured_on": null}`. Coverage takes its `list` label from the file, so a held-out result is never labelled dev. `change_detection.age_hours` is computed on the demo clock and can be negative. Summaries pass a field allowlist: no local paths, `matches`, article text, golden labels or per-item test predictions (`metrics.extraction_detector.misses` is dropped).

### 11.3 The test-split eval (D23)

`GET /api/v1/evals/test`, also served as `health.test_eval`, returns the newest eval report that is live, on the test split and not aborted:

`{status: "ok", report, created_at, split: "test", fingerprint, model, n, split_counts, fallbacks, test_runs, metrics, cards}`

- `test_runs` is the number of such reports. It should be 1.
- `cards` has the same shape as the `eval` block's cards.
- Until the test eval runs, the response is `{status: "none", note}`.
- `health.eval` keeps showing the newest report of any split. A later train run therefore replaces the test numbers in `eval`, but not in `test_eval`.


## 12. Demo mode and request guards (1 Nov; as built)

### 12.1 The demo marker: `meta.mode` and `meta.snapshot`

Every `meta` block says which data it serves. Every success body and every route error has one; the three guard errors in 12.2 answer before any route runs and have none.

```json
"meta": {
  "mode": "demo",                       // "live" for the real store
  "now": "2026-11-01T04:04:12+00:00",   // demo: frozen at the snapshot's as_of
  "api_version": "…",
  "snapshot": {                         // demo mode only; the key is absent in live mode
    "date": "2026-11-01",               // the snapshot's Brief date (Israel date): show it in the badge
    "as_of": "2026-11-01T04:04:12+00:00",
    "label": "",                        // a note the builder gave, may be empty
    "built_at": "…",
    "commit": "…"                       // the commit the snapshot was built from
  }
}
```

- The date for the badge is **`meta.snapshot.date`**, e.g. "Demo snapshot 2026-11-01".
- Live mode never has `meta.snapshot`; test `meta.mode === "demo"`, not the key's presence alone.

### 12.2 Errors the guards return

| Status | `error.code` | When |
|---|---|---|
| 403 | `demo_read_only` | Any POST, PUT, PATCH or DELETE in demo mode, before any route runs |
| 403 | `csrf_refused` | A cross-site write (`Origin` / `Sec-Fetch-Site`) in either mode |
| 400 | `untrusted_host` | A `Host` header other than localhost, 127.0.0.1, ::1 or a name in `CI_TRUSTED_HOSTS` |

These three bodies are `{"error": {code, message, details}}` with no `meta`.

## 13. Analyst actions: reopen and per-field edit notes (1 Nov; as built)

### 13.1 `POST /api/v1/items/{id}/reopen`: undo a dismiss

- **Body:** optional `{"note": "…"}`. **If-Match:** the item version, optional, as for the other actions (a stale one answers 409 `conflict`).
- **Allowed from:** `dismissed` only. Any other status answers `409 conflict` with `{status, allowed_from: ["dismissed"]}`; an unknown item `404 not_found`. In demo mode, 403 `demo_read_only`.
- **What it does:** appends a `reopen` action; the dismiss stays in the history. The decision and flag go back to what they were before the latest dismiss, so the item returns to the status it had then:

  | Status before the dismiss | After reopen |
  |---|---|
  | `awaiting_review` / `auto_published` | no decision: routing decides again, at the current level and vetted list |
  | `approved` | `approved` |
  | `flagged` | `flagged` (and the decision under the flag comes back too) |

  Edits made before or after the dismiss are kept. Nothing is written to `evals/analyst_labels.jsonl`.
- **Response:** the action envelope (`action_id`, `action: "reopen"`, `status`, `flagged`, `version`, `at`, `meta`…) plus `reopens_action_id` (the dismiss it undid) and `status_before_dismiss`.
- **Reads:** `GET /items/{id}` → `actions[]` gets `{action: "reopen", payload: {before, state_before, reopens_action_id, status_before_dismiss}}`. The Log row shows the new status, with `dismiss_reason: null`.
- From 1 Nov every item action's payload also holds `state_before: {decision, flagged}`. A dismiss logged before that has none and is restored from its `before.status` (the table above).

### 13.2 `PATCH /api/v1/items/{id}`: a note per changed field

- **Body:** `{competitor?, category?, score?, note?, notes?: {competitor?, category?, score?}}`. `notes` keys must be fields this edit changes, else `422 validation_error`. A field without its own note gets `note`. `noise` isn't an editable field.
- **Still one action** in the history: `action: "edit"`, `note` = the shared `note`, and `payload.changes: [{field, old, new, note}]`, one per changed field (`old` is the value the API showed before the edit). The response carries the same `changes`.
- **Candidates:** `evals/analyst_labels.jsonl` gets one line per changed field: `{"id", "field", "old", "new", "note", "source": "analyst", "action_id", "at"}`. Lines written before 1 Nov have the old shape: one per edit, `{"id", <field>: <new value>…, "note", "source", "at"}`, with no old value.
- **Where it shows:** `GET /items/{id}` → `actions[].payload.changes`. Log rows don't carry edits.
