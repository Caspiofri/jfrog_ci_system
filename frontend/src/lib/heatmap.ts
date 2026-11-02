// "Where competitors are active": items per competitor and category, published in the last 7 days by feed date,
// counted in the browser from Log rows (GET /log, filtered by status, competitor and collection date). Noise and
// dismissed items are excluded by status. No verdict is computed. No imports besides types, so `npm test` runs it.
import type { LogRow } from "./types";

export const HEATMAP_DAYS = 7;
export const KEPT_STATUSES = ["auto_published", "awaiting_review", "approved"]; // not noise (dropped), not dismissed

export interface HeatCell { count: number; items: LogRow[] }
export interface Heatmap {
  competitors: string[];
  categories: string[];
  cells: Record<string, Record<string, HeatCell>>; // [competitor][category]
  max: number; // the highest cell anywhere, for the colour scale
  total: number;
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
  const to = Date.parse(now);
  const from = to - days * 86_400_000;
  const seen = new Map<string, LogRow>(); // one row per item: the Log lists an item once per run that saw it
  for (const r of rows) {
    if (!r.item_id || !r.competitor || !r.category || !r.published_at) continue;
    if (!KEPT_STATUSES.includes(r.status)) continue;
    const t = Date.parse(r.published_at);
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
  for (const c of competitors) {
    const top = Math.max(0, ...categories.map((k) => cells[c][k].count));
    for (const k of categories) {
      const cell = cells[c][k];
      cell.items.sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""));
      total += cell.count;
    }
    max = Math.max(max, top);
  }
  return { competitors, categories, cells, max, total, from: new Date(from).toISOString(), to: new Date(to).toISOString() };
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
