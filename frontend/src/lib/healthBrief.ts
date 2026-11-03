// Which Brief Health's "Brief's counts" panel shows: the one anchored on the run picked in the Run filter, or the
// latest Brief when no run is picked. A picked run with no Brief of its own gives null (never another day). No imports.
export interface BriefAnchor { date: string; anchor_run_id: string }

export function briefForRun(rows: BriefAnchor[], runId: string, latest: string | null | undefined):
  { date: string | null | undefined; picked: boolean } {
  if (!runId) return { date: latest, picked: false };
  return { date: rows.find((r) => r.anchor_run_id === runId)?.date ?? null, picked: true };
}
