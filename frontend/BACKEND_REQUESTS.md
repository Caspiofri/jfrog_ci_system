# Backend requests from the frontend

Fields or endpoints the UI needs that the API contract (`docs/plans/2026-10-31-api-contract.md`) doesn't provide yet.
The frontend never edits backend code; each request waits here for Ofri.

## 1. Brief: mark a backfill (import-anchored) Brief

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
  when the page is junk. The UI hides the excerpt line when it is empty.
