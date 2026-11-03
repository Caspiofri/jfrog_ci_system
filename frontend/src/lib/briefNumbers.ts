// The Brief's "Today in numbers" tiles. Every number is a field the API returns for that Brief:
// "Collected" is items.new of the Brief run's metrics row (GET /run-metrics/{anchor_run_id}); its hover is that run's funnel
// from the row, with the values after analyst actions and the reconstructed note (D74, D78). The rest is the Brief's summary.
// No count of low-score items (published_below is left out on purpose). No imports besides types, so `npm test` runs it.
import type { BriefSummary } from "./types";

export interface RunItemCounts {
  collected?: number | null; kept?: number | null; new?: number | null; noise?: number | null; test_skip?: number | null;
  published?: number | null; held?: number | null; // at the end of the run; null on a reconstructed row (no routing ran)
}

/** The Brief run's counts, the values after analyst actions, and the reconstructed note (contract §11.1–11.2, D74, D78). */
export interface RunCounts extends RunItemCounts {
  after?: { published?: number | null; held?: number | null } | null; // items_after_actions
  reconstructedLabel?: string | null; // set only on a row rebuilt from the item log
}

export const RECONSTRUCTED_LABEL = "Reconstructed from the item log";

interface MetricsRowLike {
  run_id?: string;
  items?: RunItemCounts | null;
  items_after_actions?: { published?: number | null; held?: number | null } | null;
  reconstructed?: { label?: string } | null;
}

/** The counts of this Brief's own run, or null. A metrics row of another run (an earlier response kept while the
 *  next request is pending or failed with 404) is never used: the tile would show the wrong day's number. */
export function runCountsFor(runId: string, metrics: MetricsRowLike | null | undefined): RunCounts | null {
  if (!metrics || metrics.run_id !== runId || !metrics.items) return null;
  return {
    ...metrics.items,
    after: metrics.items_after_actions ?? null,
    reconstructedLabel: metrics.reconstructed ? metrics.reconstructed.label || RECONSTRUCTED_LABEL : null,
  };
}

export interface Tile {
  key: "new" | "published" | "high" | "review";
  label: string;
  value: number | null; // null: the API has no number for it (shown as "—")
  hint: string;
}

const levelName = (l: string) => (l ? l[0].toUpperCase() + l.slice(1) : l);

const num = (v: unknown): v is number => typeof v === "number";

/** The run's funnel: fetched → new → test items set aside → noise → published · need review. Every number is a field
 *  of the run row (or, for a row without routing fields, the Brief summary), never computed. An absent step is left
 *  out; published and held that are null (a reconstructed row) are said as not recorded, never shown as 0. The run's
 *  own values and the values after analyst actions are shown side by side (D78). */
export function funnelLine(run: RunCounts, s: BriefSummary): string {
  let outcome: string;
  if (num(run.published) && num(run.held)) {
    outcome = `${run.published} published · ${run.held} need review at the end of the run`;
    if (num(run.after?.published) && num(run.after?.held)) {
      outcome += ` · now ${run.after.published} published · ${run.after.held} need review after analyst actions`;
    }
  } else if (run.published === null || run.held === null || run.reconstructedLabel) {
    outcome = "published and need review not recorded for this run";
  } else {
    outcome = `${s.published} published · ${s.held} need review`; // a row from before routing counts were kept
  }
  const steps = [
    num(run.collected) ? `${run.collected} fetched` : null,
    num(run.new) ? `${run.new} new after removing duplicates` : null,
    num(run.test_skip) && run.test_skip > 0 ? `${run.test_skip} test items set aside, not sent to the model` : null,
    num(run.noise) ? `${run.noise} removed as noise` : null,
    outcome,
  ];
  const line = steps.filter(Boolean).join(" → ");
  return run.reconstructedLabel ? `${line} · ${run.reconstructedLabel}` : line;
}

export const NO_RUN_METRICS = "Run metrics not recorded yet for this run.";

export function todayTiles(s: BriefSummary, run: RunCounts | null | undefined): Tile[] {
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
