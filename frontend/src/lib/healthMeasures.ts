// Health measurements: each shows its own "Measured on" date (in demo mode the snapshot's "today" can be earlier than
// a measurement, so no age is shown when it would be negative). No imports, so `npm test` runs it.

/** "Measured on Nov 3, 2026"; a missing date is said in words. */
export function measuredLabel(date: string | null | undefined, fmt: (d: string) => string): string {
  return date ? `Measured on ${fmt(date)}` : "Measurement date not recorded.";
}

/** "5.5 h ago", or null when the age is unknown or negative (a measurement after the demo clock). */
export function ageLabel(hours: number | null | undefined): string | null {
  return typeof hours === "number" && hours >= 0 ? `${hours} h ago` : null;
}

/** "list": events were missed; "none": the list is present and empty; "unknown": the summary has no list. */
export function missedState(missed: unknown[] | null | undefined): "list" | "none" | "unknown" {
  if (!Array.isArray(missed)) return "unknown";
  return missed.length ? "list" : "none";
}

/** True when the coverage block holds at least one count to show. */
export function hasCoverageCounts(cv: { overall?: unknown; important?: unknown; by_source_kind?: Record<string, unknown> | null }): boolean {
  return Boolean(cv.overall || cv.important || Object.keys(cv.by_source_kind ?? {}).length);
}
