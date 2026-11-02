// The Brief's "Today in numbers" tiles. Every number is a field the API returns for that Brief:
// collected from the anchor run's metrics row (GET /run-metrics/{anchor_run_id}), the rest from the Brief's summary.
// No count of low-score items (published_below is left out on purpose). No imports besides types, so `npm test` runs it.
import type { BriefSummary } from "./types";

export interface RunItemCounts { collected?: number; kept?: number; new?: number }

export interface Tile {
  key: "collected" | "published" | "high" | "review";
  label: string;
  value: number | null; // null: the API has no number for it (shown as "—")
  hint: string;
}

const levelName = (l: string) => (l ? l[0].toUpperCase() + l.slice(1) : l);

export function todayTiles(s: BriefSummary, run: RunItemCounts | null | undefined): Tile[] {
  const collected = run?.collected ?? null;
  const fresh = run?.new ?? run?.kept;
  const unscored = s.held_by_preliminary_score?.unscored ?? 0;
  const level = levelName(s.level);
  return [
    {
      key: "collected", label: "Items collected", value: collected,
      hint: collected == null
        ? "No run record for this Brief, so the number collected isn't known."
        : `Articles this Brief's run fetched from the feeds, before duplicates and already-seen items were removed${fresh != null ? `; ${fresh} of them were new` : ""}.`,
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
