# Backend requests from the frontend

Fields or endpoints the UI needs that the API contract (`docs/plans/2026-10-31-api-contract.md`) doesn't provide yet.
The frontend never edits backend code; each request waits here for Ofri.

## 1. Brief: mark a backfill (import-anchored) Brief — done (fd6e933, `anchor_kind`)

- **Where:** `GET /api/v1/brief` → `window`, and `GET /api/v1/briefs` rows.
- **Ask:** add the anchor run's kind, e.g. `"anchor_kind": "daily" | "import"` (or `"backfill": true`).
- **Why:** the build notes (§3 Daily Brief) say the 2026-10-30 Brief is the initial 14-day import and must show as
  "Initial import (backfill)" with no "Found late" badges. The API anchors that Brief on an import run
  (contract §8) but doesn't say so in the response, and the UI must not hard-code the date.
- **UI until then:** reads `window.anchor_kind` / `anchor_kind` when present; without it every Brief renders as a
  normal daily Brief (badges shown).

## 2. Empty `excerpt` on some news items (observation, not a new field)

- On the dev copy, 11 of the 32 `google_news` items in the 2026-10-30 Brief have `excerpt: ""` (every other source has
  one); the same holds in the 2026-10-31 Brief, e.g. `402191752c14807f`. The contract says it is the first 280 characters of the stored text, or the teaser
  when the page is junk. The UI shows "Text couldn't be extracted" in its place.

## 3. Daily Brief per D44 (the contract has no D44 section yet)

Written against D44 in the PRD on Oct 31, because `docs/plans/2026-10-31-api-contract.md` had no D44 shape yet.
Field names are proposals: if the backend picks others, tell me and I'll rename on my side. Until a field lands, the
UI says the value isn't reported. Dev mock mode (`NEXT_PUBLIC_CI_MOCK=1`, see README) fills it with values marked "mock".

- **3a. Summary counts.** `GET /brief` → `summary`:
  `{"published": 3, "published_high": 0, "held": 11, "held_high": 2, "level": "strict"}`.
  `published_high` = published in the Brief with score 4–5; `held` = held for review in this Brief window at the
  current level; `held_high` = those with a preliminary score of 4–5. The UI must not count scores itself.
  Today the UI falls back to `items.total`, `kpis.important` and `counts.awaiting_review`; `held_high` has no
  fallback.
- **3b. Review filtered to a Brief window.** `GET /review?brief=2026-10-31`: only held items discovered in that
  Brief's window (`prev_anchor < discovered_at ≤ anchor`). `date_from`/`date_to` are days, and the windows run
  anchor to anchor, so they can't express it. Please echo it in `scope.brief` so the UI knows the filter applied.
- **3c. Text basis per item.** `Item.text_basis`: `{"status": "full|partial|snippet|junk", "source": "page|feed|teaser",
  "reason": "cloudflare_challenge|http_403|timeout|empty|null"}`. The UI shows it in words, e.g. "Scored from headline
  and teaser; the site blocks text extraction". `text_status` and `text_source` are already in `items.raw`; per D39,
  `reason` is new.
- **3d. Link for the lens quote.** `Item.lens.source_url` (and `source_label`): the capability sheet's Sources link
  for the lens axis, so "Why it matters to JFrog" can link the quoted line.
- **3e. Insight states.** `insights.status` adds `none_passed` (the model ran and every candidate failed the checks),
  with `rejected` as a count. `enabled: false` stays the "disabled" state. Today `none` is used for both "no
  candidate group" and "nothing passed".
- **3f. Rubric in `/meta`.** `rubric: [{"score": 5, "label": "Strategic move", "competitor": "…", "industry": "…"}]`
  from `config/rubric_v2.md`, for the score badge tooltip. Until then the UI carries the three lines (3–5) copied
  word for word from rubric v2.
- **3g. Operational counts on Health.** `GET /health` → `brief`: `{"date", "kpis": [...]}` with Found late, Mentions
  JFrog and the vs-previous values that leave the Brief. Until then Health reads `kpis` from `GET /brief`.
  Please include `prev_anchor_kind` (`"daily"` or `"import"`): when the previous Brief is the import, Health shows
  "previous Brief was the initial import" instead of a delta. Until then the UI reads `anchor_kind` from `/briefs`.
- **3h. Brief shows scores 3+ only** (D44 part 2). The UI doesn't filter, so 1s and 2s show until the API enforces it.
