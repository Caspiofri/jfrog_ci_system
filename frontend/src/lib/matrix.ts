// "JFrog vs competitors": the head-to-head cells the API already serves (GET /competitors/{key} → head_to_head),
// one row per capability, JFrog first. The UI shortens and labels values; it never compares them or guesses a
// missing one. No imports besides types, so `npm test` runs it.
import type { Cell, H2HAxis } from "./types";

export const NOT_FOUND = "Not found yet";
export const SHORT_MAX = 90;
export const SHORT_WORDS = 4;

/** The cell's data state, from the API's own `state` field: what we found on the page, never a verdict. */
export type DataState = "value" | "stale" | "not_stated" | "not_tracked";
export const STATE_INFO: Record<DataState, { label: string; icon: "check" | "clock" | "question" | "dash"; bg: string; fg: string }> = {
  value: { label: "Found", icon: "check", bg: "#eef7f0", fg: "#1f7a33" },
  stale: { label: "Stale", icon: "clock", bg: "#fff4e0", fg: "#8a5a00" },
  not_stated: { label: "Page says nothing", icon: "question", bg: "#eef0f3", fg: "#5b6576" },
  not_tracked: { label: "Not tracked yet", icon: "dash", bg: "#f8f9fb", fg: "#9aa5b5" },
};
export const STATE_ORDER: DataState[] = ["value", "stale", "not_stated", "not_tracked"];

/** The first few words of a value, for the cell; the hover has the whole text. */
export function shortWords(s: string, n = SHORT_WORDS): string {
  const w = s.replace(/\s+/g, " ").trim().split(" ");
  if (w.length <= n) return w.join(" ");
  return `${w.slice(0, n).join(" ").replace(/[\s,;:.–-]+$/, "")}…`;
}

export interface MatrixCell {
  state: DataState; // the API's state; a missing cell counts as not tracked
  short: string; // the first words of the value, or the state's label when there is no value
  text: string; // shortened value, or "Not found yet"
  full: string | null; // the whole value, for the hover
  empty: boolean;
  why: string | null; // for an empty cell: why there is no value
  source: string | null;
  asOf: string | null;
  stale: boolean;
  staleReason: string | null;
  needsReview: boolean;
  changedAt: string | null; // set only when change detection marked this cell
}

export interface MatrixRow { axis: string; label: string; jfrog: MatrixCell; cells: Record<string, MatrixCell> }

export function shorten(s: string, max = SHORT_MAX): string {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max - 1);
  const sp = cut.lastIndexOf(" ");
  return `${(sp > max * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s,;:.–-]+$/, "")}…`;
}

export function matrixCell(c: Cell | null | undefined): MatrixCell {
  const value = c && (c.state === "value" || c.state === "stale") && c.value?.trim() ? c.value.trim() : null;
  const changedAt = c?.change?.detected_at || null;
  const raw = c?.state;
  const state: DataState = raw === "value" || raw === "stale" || raw === "not_stated" || raw === "not_tracked" ? raw : "not_tracked";
  return {
    state, // as the API serves it; a missing cell counts as not tracked
    short: value ? shortWords(value) : STATE_INFO[state].label,
    text: value ? shorten(value) : NOT_FOUND,
    full: value,
    empty: !value,
    why: value ? null
      : !c ? "No head-to-head data for this competitor."
      : c.state === "not_tracked" ? `No public page is tracked for this capability${c.reason ? `: ${c.reason}` : "."}`
      : c.state === "not_stated" ? "The tracked page says nothing on this capability."
      : "No value was extracted.",
    source: c?.source_url || null,
    asOf: c?.as_of || null,
    stale: c?.state === "stale",
    staleReason: c?.state === "stale" ? c.stale_reason || null : null,
    needsReview: Boolean(c?.needs_review),
    changedAt,
  };
}

/** Rows in the API's axis order. JFrog's cell comes from the first profile that serves it for that axis. */
export function buildMatrix(profiles: { key: string; axes: H2HAxis[] | null | undefined }[]): MatrixRow[] {
  const order: { axis: string; label: string }[] = [];
  for (const p of profiles) for (const a of p.axes ?? []) if (!order.some((o) => o.axis === a.axis)) order.push({ axis: a.axis, label: a.label });
  return order.map(({ axis, label }) => {
    let jfrog: Cell | null = null;
    const cells: Record<string, MatrixCell> = {};
    for (const p of profiles) {
      const a = (p.axes ?? []).find((x) => x.axis === axis);
      if (!jfrog && a?.jfrog && a.jfrog.state !== "not_tracked") jfrog = a.jfrog;
      cells[p.key] = matrixCell(a?.competitor);
    }
    return { axis, label, jfrog: matrixCell(jfrog), cells };
  });
}

export function anyMark(rows: MatrixRow[], k: "changedAt" | "stale" | "needsReview"): boolean {
  return rows.some((r) => [r.jfrog, ...Object.values(r.cells)].some((c) => Boolean(c[k])));
}
