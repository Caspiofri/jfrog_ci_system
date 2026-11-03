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

/** D89: the one tracked competitor every cited item names, or null (mixed, missing, Industry, No tracked company,
 *  or a key the API's competitor list doesn't carry). Used beside "Competitor momentum". */
export function soleCompetitor(meta: { competitors: { key: string; is_industry?: boolean }[] } | undefined, keys: (string | null | undefined)[]): string | null {
  if (!meta || !keys.length || keys.some((k) => !k)) return null;
  const set = new Set(keys);
  if (set.size !== 1) return null;
  const k = keys[0]!;
  const c = meta.competitors.find((x) => x.key === k);
  return c && !c.is_industry && k !== "industry" && k !== NONE_KEY ? k : null;
}
