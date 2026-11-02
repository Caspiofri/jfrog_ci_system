// "Mentions JFrog": the API holds only a flag (mentions_jfrog) and the item's 280-character excerpt. When the excerpt
// itself contains JFrog, show that sentence; otherwise a plain statement. No API call, no model. No imports.
export const MENTION_FALLBACK = "The article text mentions JFrog.";

/** The sentence of the excerpt that names JFrog, or null when the excerpt doesn't. */
export function jfrogSentence(excerpt: string | null | undefined): string | null {
  const t = (excerpt ?? "").replace(/\s+/g, " ").trim();
  if (!/jfrog/i.test(t)) return null;
  const sentences = t.match(/[^.!?…]+[.!?…]*/g) ?? [t];
  const hit = sentences.find((s) => /jfrog/i.test(s));
  return hit ? hit.trim() : null;
}

export function mentionHint(excerpt: string | null | undefined): string {
  const s = jfrogSentence(excerpt);
  return s ? `In the excerpt: “${s}”` : MENTION_FALLBACK;
}

/** The drawer's "Why it matters to JFrog" block shows only when there is a lens result or the lens failed. */
export function showLensBlock(lens: unknown, status: string | null | undefined): boolean {
  return Boolean(lens) || status === "rejected" || status === "failed";
}
