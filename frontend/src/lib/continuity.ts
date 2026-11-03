// Insight continuity badges (contract §14). The API decides the status; the UI only words it.
// "since" is the previous Brief's date, not when the pattern started, so the wording says "prev. Brief" (D89).
// Older data has no continuity field: no badge, no line, no error. No imports besides types, so `npm test` runs it.
import type { InsightContinuity, PreviousInsights } from "./types";

export const CONTINUITY_TIP = "Matched to an insight of the previous Brief by shared cited stories.";

export interface Badge { status: "new" | "continuing" | "strengthened"; text: string }

export function continuityBadge(c: InsightContinuity | null | undefined, fmt: (date: string) => string): Badge | null {
  if (!c || typeof c !== "object") return null;
  if (c.status === "new") return { status: "new", text: "New" };
  if (c.status !== "continuing" && c.status !== "strengthened") return null;
  if (!c.since) return null; // a match always names the previous Brief; without it the badge would mislead
  const base = `prev. Brief (${fmt(c.since)})`;
  if (c.status === "continuing") return { status: "continuing", text: base };
  const n = Number(c.new_stories ?? 0);
  if (!(n > 0)) return { status: "continuing", text: base };
  return { status: "strengthened", text: `${base} · +${n} new source${n === 1 ? "" : "s"}` };
}

/** "<N> of the previous Brief's insights no longer appear", only when N > 0. */
export function goneLine(p: PreviousInsights | null | undefined): string | null {
  const n = Number(p?.unmatched ?? 0);
  if (!p || !(n > 0)) return null;
  return `${n} of the previous Brief's insights no longer appear`;
}

export const NEW_SOURCE_TIP = (date: string) => `Cited now, not by this insight in the previous Brief (${date}).`;

/** D89: which cited articles are the "+N new source(s)". A story is new when no matched insight of the previous Brief
 *  cited it (current story_ids minus the matched insights' story_ids, both from the API). Returned only when that
 *  count equals the API's new_stories and every new story is a cited article, so a chip never contradicts the badge. */
export function newCitedIds(
  ins: { story_ids?: string[]; item_ids?: string[]; continuity?: InsightContinuity | null },
  previous: { insight_id: string; story_ids?: string[] }[] | null | undefined,
): Set<string> | null {
  const c = ins.continuity;
  if (!c || c.status !== "strengthened" || !previous) return null;
  const n = Number(c.new_stories ?? 0);
  const matched = new Set(c.matched ?? []);
  const prev = previous.filter((p) => matched.has(p.insight_id));
  if (!(n > 0) || !matched.size || prev.length !== matched.size) return null;
  const seen = new Set(prev.flatMap((p) => p.story_ids ?? []));
  const fresh = [...new Set(ins.story_ids ?? [])].filter((s) => !seen.has(s));
  const cited = new Set(ins.item_ids ?? []);
  if (fresh.length !== n || !fresh.every((s) => cited.has(s))) return null;
  return new Set(fresh);
}
