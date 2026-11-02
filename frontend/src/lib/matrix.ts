// "JFrog vs competitors": the head-to-head cells the API already serves (GET /competitors/{key} → head_to_head),
// one row per capability, JFrog first. The UI shortens and labels values; it never compares them or guesses a
// missing one. No imports besides types, so `npm test` runs it.
import type { Cell, H2HAxis } from "./types";

export const NOT_FOUND = "Not found yet";
export const SHORT_MAX = 90;

export interface MatrixCell {
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
  return {
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
