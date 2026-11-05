# Jessi web UI (Next.js)

<img src="public/brand/jessi-full-light.svg" alt="Jessi: JFrog's Engine for Strategic Signals & Intelligence" width="360">

Jessi is JFrog's Engine for Strategic Signals & Intelligence (D46).

The CI tool's web UI: Next.js + Tailwind + shadcn/ui + Recharts (D3). Every number comes from the CI API
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

### Dev mock mode (state scenarios)

The D44 fields are all served by the API now (contract §10), so mock mode no longer fills anything in real views.
`NEXT_PUBLIC_CI_MOCK=1 NEXT_DIST_DIR=.next-mock npx next dev -p 3012` enables state scenarios for windows the data
doesn't have: on the Brief, `?mock=empty|all_held` and `?mock_insights=disabled|refreshing|failed|none_passed|not_run`.
Every invented value is marked "mock".

Mock mode is local `next dev` only, and separate from demo mode (`CI_MODE=demo`, a frozen real snapshot):
- `next.config.ts` refuses `next build`, `next start` and demo mode when `NEXT_PUBLIC_CI_MOCK` is set.
- The mock code is stripped from production bundles. `npm run build` and `build:check` fail if any of it remains.
- At runtime, mock stays off until `/meta` reports `mode: "live"`.
- `.dockerignore` keeps env files and `public/mock/` out of images.
- `npm test` checks all of this.

## Brand (D46)

`public/brand/` holds the logo files. Each is the original SVG with only the root attributes changed (viewBox set,
width/height removed), so they are transparent and scale freely:
- `jessi-full.svg`: logo with the white tagline, for dark backgrounds. `jessi-full-light.svg`: the same with the
  tagline in #1f2937, for light backgrounds.
- `jessi-mark.svg`: splash and wordmark, no tagline groups. Used in the app header at 40px high.
- `jessi-icon.svg`: the favicon, viewBox cropped to the splash. `jessi-icon-32.png` is its 32px fallback.

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
