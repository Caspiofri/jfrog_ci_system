// "Where competitors are active": items per competitor and category, counted exactly as the competitor cards' big
// number (GET /competitors items_7d): published items, by the date found (discovered_at), in the cards' 7-day window.
// So a column's total is that card's number. Awaiting-review items stay on the cards' own tag. Counted in the browser from Log
// rows; noise and dismissed items are excluded by status. No imports besides types, so `npm test` runs it.
import type { LogRow } from "./types";

export const HEATMAP_DAYS = 7;
// the API's published statuses (ci/api/service.py PUBLISHED): not awaiting review, not noise (dropped), not dismissed
export const KEPT_STATUSES = ["auto_published", "approved", "flagged"];

export interface HeatCell { count: number; items: LogRow[] }
export interface Heatmap {
  colTotals: Record<string, number>; // per competitor: equals the card's number
  competitors: string[];
  categories: string[];
  cells: Record<string, Record<string, HeatCell>>; // [competitor][category]
  max: number; // the highest cell anywhere, for the colour scale
  total: number;
  published: number; // of total: published (the cards' big numbers)
  queued: number; // of total: awaiting review (the cards' "awaiting review" tags)
  from: string; // window start (exclusive), ISO
  to: string; // window end (inclusive), ISO: the API's "now"
}

/** GET /log query: kept statuses, the six competitors, collected on or after the window's first day (an item is
 *  never collected before its feed date, so nothing in the window is cut). */
export function heatmapQuery(competitors: string[], now: string, days = HEATMAP_DAYS) {
  const start = new Date(Date.parse(now) - days * 86_400_000);
  return { status: KEPT_STATUSES, competitor: competitors, date_from: start.toISOString().slice(0, 10), limit: 200, offset: 0 };
}

export function buildHeatmap(rows: LogRow[], competitors: string[], categories: string[], now: string, days = HEATMAP_DAYS): Heatmap {
  const to = Date.parse(now); // the cards' week.end
  const from = to - days * 86_400_000; // the cards' week.start
  const seen = new Map<string, LogRow>(); // one row per item: the Log lists an item once per run that saw it
  for (const r of rows) {
    if (!r.item_id || !r.competitor || !r.category || !r.discovered_at) continue;
    if (!KEPT_STATUSES.includes(r.status)) continue;
    const t = Date.parse(r.discovered_at); // the date found, as the cards count
    if (!(t > from && t <= to)) continue;
    if (!seen.has(r.item_id)) seen.set(r.item_id, r);
  }
  const cells: Heatmap["cells"] = {};
  for (const c of competitors) {
    cells[c] = {};
    for (const k of categories) cells[c][k] = { count: 0, items: [] };
  }
  for (const r of seen.values()) {
    const cell = cells[r.competitor!]?.[r.category!];
    if (cell) { cell.count += 1; cell.items.push(r); }
  }
  let max = 0;
  let total = 0;
  let queued = 0;
  for (const c of competitors) {
    const top = Math.max(0, ...categories.map((k) => cells[c][k].count));
    for (const k of categories) {
      const cell = cells[c][k];
      cell.items.sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""));
      total += cell.count;
      queued += cell.items.filter((r) => r.status === "awaiting_review").length;
    }
    max = Math.max(max, top);
  }
  const colTotals = Object.fromEntries(competitors.map((c) => [c, categories.reduce((t, k) => t + cells[c][k].count, 0)]));
  return { colTotals, competitors, categories, cells, max, total, published: total - queued, queued, from: new Date(from).toISOString(), to: new Date(to).toISOString() };
}

/** One colour, light to strong by count; 0 is an empty light cell. */
export const HEAT_RGB = [63, 91, 143]; // the app's navy-blue
export const ZERO_BG = "#f6f8fb";
export function heatColor(count: number, max: number): { bg: string; fg: string } {
  if (count <= 0 || max <= 0) return { bg: ZERO_BG, fg: "#9aa5b5" };
  const a = 0.15 + 0.85 * (count / max);
  return { bg: `rgba(${HEAT_RGB.join(", ")}, ${a.toFixed(2)})`, fg: a > 0.55 ? "#ffffff" : "#1f2937" };
}

/** Legend steps: 1, the middle and the highest count (distinct, ascending). */
export function legendSteps(max: number): number[] {
  if (max <= 0) return [];
  return [...new Set([1, Math.round(max / 2), max])].filter((n) => n >= 1).sort((a, b) => a - b);
}
