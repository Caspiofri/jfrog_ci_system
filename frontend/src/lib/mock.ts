// Dev-only stand-ins for D44 fields the API doesn't serve yet (BACKEND_REQUESTS.md #3).
// Off unless NEXT_PUBLIC_CI_MOCK=1. Every filled value is listed in `mock` and shown on screen as "mock".
// Remove a block here when its field lands in the API.
import { useApi } from "@/lib/api";
import type { Brief, Item, Lens, TextBasis } from "@/lib/types";

export const MOCK = process.env.NEXT_PUBLIC_CI_MOCK === "1";

/** Real text_status/text_source per item, exported from the dev store copy (public/mock/, gitignored). */
export function useMockTextBasis() {
  return useApi<Record<string, TextBasis>>(MOCK ? "/mock/text-basis.local.json" : null, { shouldRetryOnError: false });
}

/** One sample lens so the card can be checked before the first run that stores lenses (Nov 1, 06:00).
 * The quote is word for word from config/jfrog_capabilities.md (Curation / gating row). */
const SAMPLE_LENS: Lens = {
  axis: "curation_gating",
  capability_quote: "blocks malicious, vulnerable, license-violating and immature packages (default 14-day hold)",
  relation: "closes_gap",
  why: "A package firewall at install time is what JFrog Curation sells; GitHub now offers it for npm.",
  source_url: "https://jfrog.com/curation/",
  source_label: "JFrog Curation",
};
const SAMPLE_LENS_TITLE = /package firewall/i;

function fillItem(it: Item, basis: Record<string, TextBasis> | undefined, lensId: string | null): Item {
  const mock: string[] = [];
  let out = it;
  if (it.text_basis === undefined && basis?.[it.item_id]) {
    out = { ...out, text_basis: basis[it.item_id] };
    mock.push("text_basis");
  }
  if (!it.lens && it.item_id === lensId) {
    out = { ...out, lens: SAMPLE_LENS };
    mock.push("lens");
  }
  return mock.length ? { ...out, mock } : out;
}

/** Scenarios for checking states without a matching real window: ?mock=empty | all_held; ?mock_insights=… */
export function mockBrief(b: Brief, scenario: string, insights: string, basis: Record<string, TextBasis> | undefined): Brief {
  if (!MOCK) return b;
  let out: Brief = b;
  if (scenario === "empty" || scenario === "all_held") {
    const held = scenario === "all_held" ? 11 : 0;
    out = {
      ...b,
      summary: { published: 0, published_high: 0, held, held_high: scenario === "all_held" ? 2 : 0, level: "strict", mock: ["all"] },
      items: { ...b.items, total: 0, offset: 0, items: [] },
      insights: { status: "none", rejected: 0, items: [], enabled: true, mock: true },
    };
  } else {
    const lensId = b.items.items.find((it) => SAMPLE_LENS_TITLE.test(it.title))?.item_id ?? null;
    out = { ...b, items: { ...b.items, items: b.items.items.map((it) => fillItem(it, basis, lensId)) } };
    if (!b.summary) {
      // published / published_high / held come from fields the API already serves; held_high has no source yet.
      const important = b.kpis.find((k) => k.key === "important")?.value ?? null;
      out.summary = { published: b.items.total, published_high: important, held: b.counts?.awaiting_review ?? 0, held_high: 2, level: b.level, mock: ["held_high"] };
    }
  }
  if (insights) {
    const ins = { ...out.insights, items: [], mock: true };
    if (insights === "disabled") out = { ...out, insights: { ...ins, enabled: false, status: "not_generated" } };
    else if (insights === "failed") out = { ...out, insights: { ...ins, status: "failed" } };
    else if (insights === "none_passed") out = { ...out, insights: { ...ins, status: "none_passed", rejected: 3 } };
  }
  return out;
}
