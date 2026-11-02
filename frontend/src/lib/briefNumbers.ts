// The Brief's "Today in numbers" tiles. Every number is a field the API returns for that Brief:
// "New items" is items.new of the Brief run's metrics row (GET /run-metrics/{anchor_run_id}); the rest is the Brief's summary.
// No count of low-score items (published_below is left out on purpose). No imports besides types, so `npm test` runs it.
import type { BriefSummary } from "./types";

export interface RunItemCounts { collected?: number; kept?: number; new?: number }

/** The counts of this Brief's own run, or null. A metrics row of another run (an earlier response kept while the
 *  next request is pending or failed with 404) is never used: the tile would show the wrong day's number. */
export function runCountsFor(runId: string, metrics: { run_id?: string; items?: RunItemCounts | null } | null | undefined): RunItemCounts | null {
  if (!metrics || metrics.run_id !== runId) return null;
  return metrics.items ?? null;
}

export interface Tile {
  key: "new" | "published" | "high" | "review";
  label: string;
  value: number | null; // null: the API has no number for it (shown as "—")
  hint: string;
}

const levelName = (l: string) => (l ? l[0].toUpperCase() + l.slice(1) : l);

export function todayTiles(s: BriefSummary, run: RunItemCounts | null | undefined): Tile[] {
  const fresh = typeof run?.new === "number" ? run.new : null;
  const unscored = s.held_by_preliminary_score?.unscored ?? 0;
  const level = levelName(s.level);
  return [
    {
      key: "new", label: "New items", value: fresh,
      hint: fresh == null ? "No run record for this Brief, so the number of new items isn't known." : "Collected since the previous Brief.",
    },
    {
      key: "published", label: "Published", value: s.published,
      hint: `Items in this Brief: published and scored ${s.brief_min_score} or higher, automatically or after an analyst approved them.`,
    },
    {
      key: "high", label: "High score (4+)", value: s.published_high,
      hint: "Of the published items, those scored 4 (material change) or 5 (strategic move).",
    },
    {
      key: "review", label: "Needs review", value: s.held,
      hint: `Found in this window and held at ${level} for an analyst; not verified, so not in the Brief yet. ${s.held_high} preliminarily scored 4–5${unscored ? `, ${unscored} not scored (a model failure)` : ""}.`,
    },
  ];
}
