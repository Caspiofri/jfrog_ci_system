# Jessie web UI (Next.js)

The CI tool's web UI: Next.js + Tailwind + shadcn/ui + Recharts (PRD D3). Every number comes from the CI API
(`docs/plans/2026-10-31-api-contract.md`); no screen has sample data except the Roadmap tab.

## Run (dev)

1. Start the CI API. For UI work, run it from a worktree that holds a **copy** of the store, so analyst actions
   never touch the real `data/ci/ci.sqlite`:

   ```bash
   python -m ci.api --port 8011
   ```

2. Start the UI. `/api/v1/*` is forwarded to `CI_API_URL` (default `http://127.0.0.1:8011`), so the API needs no CORS.

   ```bash
   cd frontend
   npm install
   npm run dev -- -p 3011        # or: CI_API_URL=http://127.0.0.1:8010 npm run dev
   ```

For `npm run build && npm start`, set `CI_API_URL` at **build** time: Next.js writes the rewrite into the build.

To check a production build while `npm run dev` is running, use `npm run build:check`: it builds into
`.next-build/`. A plain `npm run build` writes `.next/` and breaks a running dev server.

### Dev mock mode (D44 fields the API doesn't serve yet)

`NEXT_PUBLIC_CI_MOCK=1 NEXT_DIST_DIR=.next-mock npx next dev -p 3012` fills the missing D44 fields
(`BACKEND_REQUESTS.md` #3) with stand-ins, each marked "mock" on screen. Off by default. On the Brief:
`?mock=empty` or `?mock=all_held` shows those windows, and `?mock_insights=disabled|failed|none_passed` shows those
insight states. The text basis comes from `public/mock/text-basis.local.json` (gitignored), exported from the local
store copy. Delete each block in `src/lib/mock.ts` once its field lands.

## Rules

- API strings are untrusted (D32): rendered as React text only. ESLint fails on `dangerouslySetInnerHTML` and
  `innerHTML`, and links open only for `http(s)` URLs.
- Every API call has loading, empty and error states (`src/components/ci.tsx`, `Async`).
- Fields the UI needs and the API lacks go to `BACKEND_REQUESTS.md`.

## Roadmap screenshots

The Roadmap tab (`/roadmap`) shows concept screens from the design prototype, each labeled "Concept, sample data".
Add each screenshot as `public/roadmap/<slug>.png`; until then the card shows a placeholder naming the file.
Slugs: `market-view`, `topics`, `emerging`, `reactions`, `deal-extraction`, `strength-radar`, `convergence`,
`team-chips`, `battlefield`.
