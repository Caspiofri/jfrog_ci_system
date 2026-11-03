"use client";
import { competitorDisplayName } from "./competitorLabel";
import { useApi } from "@/lib/api";
import type { Meta } from "@/lib/types";

/** /meta is shared by every screen (competitor names, categories, levels). One SWR key, fetched once. */
export function useMeta() {
  return useApi<Meta>("/api/v1/meta", { revalidateOnMount: true, dedupingInterval: 60_000 });
}

export function competitorName(meta: Meta | undefined, key: string | null | undefined): string {
  return competitorDisplayName(meta, key);
}

/** "20261031T1345Z-802913" → ISO time, for display only. */
export function runTime(runId: string | null | undefined): string | null {
  const m = runId?.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})Z/);
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00Z` : null;
}
