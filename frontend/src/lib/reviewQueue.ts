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

export type QueueSort = "" | "newest" | "oldest";

/** The sort selector. "" is Importance, the API's own order (the default). */
export const SORT_OPTIONS: { value: QueueSort; label: string }[] = [
  { value: "", label: "Importance" },
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
];

/** The line under the filters, for each sort. */
export const SORT_LINES: Record<QueueSort, string> = {
  "": SORT_ORDER_LINE,
  newest: "Newest feed date first. Changed head-to-head cells first, since they have no feed date; items without a feed date last.",
  oldest: "Oldest feed date first. Changed head-to-head cells first, since they have no feed date; items without a feed date last.",
};

/** Sorts the whole queue in the browser (every page is fetched). Changed cells keep the top, in the API's order; items
 *  sort by feed date (published_at), those without one last; equal dates keep the API's order. Never mutates rows. */
export function sortQueue<T extends Row>(rows: T[], sort: string): T[] {
  if (sort !== "newest" && sort !== "oldest") return rows;
  const dir = sort === "newest" ? -1 : 1;
  const changes = rows.filter((r) => r.kind === "change");
  const items = rows.map((r, i) => ({ r, i })).filter((x) => x.r.kind === "item");
  const t = (r: T) => {
    const v = r.kind === "item" ? Date.parse(r.item.published_at ?? "") : NaN;
    return Number.isNaN(v) ? null : v;
  };
  items.sort((a, b) => {
    const ta = t(a.r), tb = t(b.r);
    if (ta == null || tb == null) return ta == null && tb == null ? a.i - b.i : ta == null ? 1 : -1;
    return ta === tb ? a.i - b.i : dir * (ta - tb);
  });
  return [...changes, ...items.map((x) => x.r)];
}

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

// ---- D91: which items the queue lists, by decision ----

/** "" is Needs decision, the default: GET /review, items no analyst approved or dismissed yet. */
export type DecisionView = "" | "approved" | "dismissed" | "all";
/** Decided statuses, read from GET /log (the queue endpoint lists only awaiting_review). Flagged is published by an
 *  analyst's flag; it has no option of its own and shows under All. */
export const DECIDED_STATUSES = ["approved", "dismissed", "flagged"];

/** Each decided item once (the Log lists an item once per run that saw it), in the Log's order. */
export function decidedIds(rows: { item_id: string | null; status: string }[]): string[] {
  const seen = new Set<string>();
  for (const r of rows) if (r.item_id && DECIDED_STATUSES.includes(r.status)) seen.add(r.item_id);
  return [...seen];
}

/** The same scope GET /review applies, for decided items: the Brief window (discovered in (prev_anchor, anchor]) and
 *  the hold reason at the shown level. Competitor is already a GET /log parameter. */
export function inQueueScope(
  it: { discovered_at: string | null; hold_reasons: { code: string; held_at: string[] }[] },
  s: { window?: { prev_anchor: string; anchor: string } | null; reason?: string; level: string },
): boolean {
  if (s.window) {
    const t = Date.parse(it.discovered_at ?? "");
    if (!(t > Date.parse(s.window.prev_anchor) && t <= Date.parse(s.window.anchor))) return false;
  }
  if (s.reason && !it.hold_reasons.some((h) => h.code === s.reason && h.held_at.includes(s.level))) return false;
  return true;
}

/** The filter's options with their counts. Dismissed only when the data carries dismissed items. */
export function decisionOptions(n: { needs: number; approved: number; dismissed: number; all: number }, hasDismissed: boolean) {
  return [
    { value: "" as DecisionView, label: `Needs decision (${n.needs})` },
    { value: "approved" as DecisionView, label: `Approved (${n.approved})` },
    ...(hasDismissed ? [{ value: "dismissed" as DecisionView, label: `Dismissed (${n.dismissed})` }] : []),
    { value: "all" as DecisionView, label: `All (${n.all})` },
  ];
}
