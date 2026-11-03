// The drawer's "Classified by" line: a short plain label ("AI model" or "rules"); the method and reason the API returns
// go into its hover. Method values are ci/classify.py's. No imports, so `npm test` runs it.

export interface ClassificationLike { method?: string; reason?: string }

const LABEL: Record<string, string> = {
  llm: "AI model",
  rules: "rules",
  prefilter: "rules", // the rule-based noise prefilter
  fallback: "AI model gave no usable answer", // the prefilled competitor was kept; the item goes to review
};

export function classifiedBy(c: ClassificationLike | null | undefined): { label: string; hint: string | null } {
  if (!c?.method) return { label: "—", hint: null };
  return { label: LABEL[c.method] ?? c.method, hint: c.reason ? `${c.method} · ${c.reason}` : c.method };
}
