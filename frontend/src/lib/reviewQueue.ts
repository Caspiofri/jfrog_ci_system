// Review queue: search, score and category filters over the whole held queue, done in the browser.
// The API filters by level, Brief window, competitor and hold reason; it has no text search, score or
// category parameter, so the page fetches the whole queue (every page) and narrows it here.
// No imports besides types, so `npm test` runs this file directly under node.
import type { ReviewChangeRow, ReviewItemRow } from "./types";

type Row = ReviewItemRow | ReviewChangeRow;

/** The API's page size cap (ci/api/app.py MAX_LIMIT). */
export const FETCH_LIMIT = 200;

/** The order GET /review returns, stated as ci/api/app.py sorts it. */
export const SORT_ORDER_LINE =
  "Sorted as the API returns them: changed head-to-head cells first, then items held at every level, then score from high to low, then oldest discovered first.";

export const SCORE_OPTIONS = [
  { value: "4+", label: "Score 4–5" },
  { value: "3", label: "Score 3" },
  { value: "2", label: "Score 2" },
  { value: "1", label: "Score 1" },
  { value: "none", label: "Not scored" },
];

export interface LocalFilters {
  q: string;
  score: string; // "" | "4+" | "3" | "2" | "1" | "none"
  category: string; // "" or a category name
}

/** Item id (full or prefix), title and publisher, case-insensitive. Changed cells match on id, competitor and axis. */
export function matchesSearch(row: Row, q: string): boolean {
  const s = q.trim().toLowerCase();
  if (!s) return true;
  if (row.kind === "change") {
    return [row.change_id, row.competitor, row.axis, row.axis_label].some((v) => (v ?? "").toLowerCase().includes(s));
  }
  const it = row.item;
  if (it.item_id.toLowerCase().startsWith(s)) return true;
  return [it.title, it.publisher, it.publisher_host].some((v) => (v ?? "").toLowerCase().includes(s));
}

export function matchesScore(row: Row, score: string): boolean {
  if (!score) return true;
  if (row.kind === "change") return false; // a changed cell has no score
  const n = row.item.score;
  if (score === "none") return n == null;
  if (n == null) return false;
  if (score === "4+") return n >= 4;
  return n === Number(score);
}

export function matchesCategory(row: Row, category: string): boolean {
  if (!category) return true;
  return row.kind === "item" && row.item.category === category;
}

/** Keeps the API's order. */
export function filterQueue<T extends Row>(rows: T[], f: LocalFilters): T[] {
  return rows.filter((r) => matchesSearch(r, f.q) && matchesScore(r, f.score) && matchesCategory(r, f.category));
}

export function hasLocalFilters(f: LocalFilters): boolean {
  return Boolean(f.q.trim() || f.score || f.category);
}

/** The window selector: "All held items" ("" = no brief param) or one Brief day, newest first. */
export function windowOptions(dates: string[], fmt: (d: string) => string): { value: string; label: string }[] {
  return [...new Set(dates)].sort().reverse().map((d) => ({ value: d, label: `Held from the Brief of ${fmt(d)}` }));
}

/** Query for GET /review: the API-side filters, the largest page. `brief` is omitted for "All held items". */
export function queueQuery(s: { level?: string; reason?: string; competitor?: string; brief?: string }, offset = 0) {
  return {
    level: s.level || undefined,
    reason: s.reason || undefined,
    competitor: s.competitor || undefined,
    brief: s.brief || undefined,
    limit: FETCH_LIMIT,
    offset,
  };
}

/** Offsets still to fetch after the first page so the whole queue is in hand. */
export function remainingOffsets(total: number, got: number): number[] {
  const out: number[] = [];
  for (let o = got; o < total; o += FETCH_LIMIT) out.push(o);
  return out;
}
