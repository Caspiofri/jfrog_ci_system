// Dev-only state scenarios for the Brief, for windows the real data doesn't have (an empty or all-held window,
// each insight state). Every D44 field is now served by the API (contract §10), so nothing here fills real views:
// the scenarios replace the whole response and the page says so, with every value marked "mock".
// Off unless NEXT_PUBLIC_CI_MOCK=1 under `next dev`. Never in a production build, `next start` or demo mode:
// next.config.ts refuses those, NODE_ENV below strips the code from production bundles, and useMock() stays off
// until the API says it is live (never in demo, a frozen real snapshot). Tested by `npm test`.
import { useMeta } from "@/lib/meta";
import type { Brief, BriefSummary } from "@/lib/types";

export const MOCK = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_CI_MOCK === "1";

/** Mock is active only with the flag and once /meta confirms a live API: off while loading and in demo mode. */
export function useMock(): boolean {
  const { data } = useMeta();
  return MOCK && data?.meta?.mode === "live";
}

const ZERO = { "5": 0, "4": 0, "3": 0, "<=2": 0, noise: 0 };

/** ?mock=empty | all_held replaces the window; ?mock_insights=disabled | refreshing | failed | none_passed | not_run. */
export function mockBrief(on: boolean, b: Brief, scenario: string, insights: string): Brief {
  if (!on || !MOCK) return b;
  let out: Brief = b;
  if (scenario === "empty" || scenario === "all_held") {
    const held = scenario === "all_held";
    const summary: BriefSummary = {
      brief_min_score: 3, published: 0, published_high: 0, published_below: 0,
      held: held ? 11 : 0, held_high: held ? 4 : 0,
      held_by_preliminary_score: held ? { ...ZERO, "4": 4, "3": 4, "<=2": 3 } : ZERO,
      level: "strict", mock: true,
    };
    out = {
      ...b, summary,
      items: { ...b.items, total: 0, offset: 0, items: [] },
      insights: { status: "none_passed", rejected: 0, items: [], enabled: true, mock: true },
    };
  }
  if (insights) {
    out = { ...out, insights: { ...out.insights, status: insights, rejected: insights === "none_passed" ? 3 : 0, items: [], enabled: insights !== "disabled", mock: true } };
  }
  return out;
}
