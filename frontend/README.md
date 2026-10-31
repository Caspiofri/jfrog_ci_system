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
