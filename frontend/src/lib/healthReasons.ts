// A Health panel is never silently blank: with no data it says why, in a few words. In demo mode the snapshot
// may leave out what the live system has (eval reports, coverage, change detection). No imports, so `npm test` runs it.

export const NOT_IN_SNAPSHOT = "Not included in this demo snapshot.";
export const NOT_MEASURED = "Not measured yet.";

export function noDataReason(mode: string | undefined): string {
  return mode === "demo" ? NOT_IN_SNAPSHOT : NOT_MEASURED;
}
