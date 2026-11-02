// Insight continuity badges (contract §14). The API decides the status; the UI only words it.
// "since" is the previous Brief's date, not when the pattern started, so the wording says "previous Brief".
// Older data has no continuity field: no badge, no line, no error. No imports besides types, so `npm test` runs it.
import type { InsightContinuity, PreviousInsights } from "./types";

export const CONTINUITY_TIP = "Matched to an insight of the previous Brief by shared cited stories.";

export interface Badge { status: "new" | "continuing" | "strengthened"; text: string }

export function continuityBadge(c: InsightContinuity | null | undefined, fmt: (date: string) => string): Badge | null {
  if (!c || typeof c !== "object") return null;
  if (c.status === "new") return { status: "new", text: "New" };
  if (c.status !== "continuing" && c.status !== "strengthened") return null;
  if (!c.since) return null; // a match always names the previous Brief; without it the badge would mislead
  const base = `Also in previous Brief (${fmt(c.since)})`;
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
