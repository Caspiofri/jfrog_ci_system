// Display only: the competitor value "none" (nothing we track; D70) reads "No tracked company" on every screen and in
// every filter. The value sent to the API stays "none"; "industry" (market news without a tracked competitor) keeps its
// own name. No imports, so `npm test` runs it.

export const NONE_KEY = "none";
export const NONE_LABEL = "No tracked company";

interface MetaLike { competitors: { key: string; name: string }[] }

export function competitorDisplayName(meta: MetaLike | undefined, key: string | null | undefined): string {
  if (!key) return "—";
  if (key === NONE_KEY) return NONE_LABEL;
  return meta?.competitors.find((c) => c.key === key)?.name ?? key;
}

/** Competitor filter options: the API's competitors, then "No tracked company" (value "none"). */
export function competitorFilterOptions(meta: MetaLike | undefined): { value: string; label: string }[] {
  const opts = (meta?.competitors ?? []).filter((c) => c.key !== NONE_KEY).map((c) => ({ value: c.key, label: c.name }));
  return [...opts, { value: NONE_KEY, label: NONE_LABEL }];
}
