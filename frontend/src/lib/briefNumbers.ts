// The Brief's "Today in numbers" tiles. Every number is a field the API returns for that Brief:
// "Collected" is items.new of the Brief run's metrics row (GET /run-metrics/{anchor_run_id}); its hover is that run's funnel
// (fetched, new, noise from the row; published and need review from the Brief summary). The rest is the Brief's summary.
// No count of low-score items (published_below is left out on purpose). No imports besides types, so `npm test` runs it.
import type { BriefSummary } from "./types";

export interface RunItemCounts { collected?: number | null; kept?: number | null; new?: number | null; noise?: number | null }

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

const num = (v: unknown): v is number => typeof v === "number";

/** "239 fetched → 26 new after removing duplicates → 11 removed as noise → 4 published · 11 need review". Every number
 *  is a field of the run row or the Brief summary, never computed; a step whose field is empty is left out. */
export function funnelLine(run: RunItemCounts, s: BriefSummary): string {
  const steps = [
    num(run.collected) ? `${run.collected} fetched` : null,
    num(run.new) ? `${run.new} new after removing duplicates` : null,
    num(run.noise) ? `${run.noise} removed as noise` : null,
    `${s.published} published · ${s.held} need review`,
  ];
  return steps.filter(Boolean).join(" → ");
}

// TODO: add "Reconstructed from the item log" to the Collected hover when the run-metrics row carries BE's
// reconstructed marker (30 and 31 Oct, D74). The field isn't in the API contract yet, so nothing is shown.
export const NO_RUN_METRICS = "Run metrics not recorded yet for this run.";

export function todayTiles(s: BriefSummary, run: RunItemCounts | null | undefined): Tile[] {
  const fresh = num(run?.new) ? run.new : null;
  const unscored = s.held_by_preliminary_score?.unscored ?? 0;
  const level = levelName(s.level);
  return [
    {
      key: "new", label: "Collected", value: fresh,
      hint: fresh == null || !run ? NO_RUN_METRICS : funnelLine(run, s),
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
