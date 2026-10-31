import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

// The browser calls /api/v1/* on the Next server, which forwards to the CI API.
// Same origin, so the backend needs no CORS. Dev API: python -m ci.api --port 8011 (run in the worktree).
const API = process.env.CI_API_URL ?? "http://127.0.0.1:8011";

/** Mock mode fills invented values (src/lib/mock.ts). It exists for local dev only: a production build, `next start`
 * and demo mode (CI_MODE=demo, a frozen real snapshot) must never carry it. Checked by `npm test`. */
export function assertNoMock(phase: string, env: NodeJS.ProcessEnv): void {
  const mock = env.NEXT_PUBLIC_CI_MOCK;
  if (mock === undefined || mock === "") return;
  if (phase !== PHASE_DEVELOPMENT_SERVER) {
    throw new Error(`NEXT_PUBLIC_CI_MOCK is set (${JSON.stringify(mock)}) for ${phase}: mock mode is for local \`next dev\` only. Unset it.`);
  }
  if (env.CI_MODE === "demo") {
    throw new Error("NEXT_PUBLIC_CI_MOCK is set together with CI_MODE=demo: demo mode shows a frozen real snapshot, never mock values. Unset it.");
  }
}

export default function config(phase: string): NextConfig {
  assertNoMock(phase, process.env);
  return {
    // A check build goes to its own folder (npm run build:check), so it never overwrites the dev server's .next.
    distDir: process.env.NEXT_DIST_DIR || ".next",
    async rewrites() {
      return [{ source: "/api/v1/:path*", destination: `${API}/api/v1/:path*` }];
    },
  };
}
