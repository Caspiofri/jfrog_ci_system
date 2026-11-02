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

export interface MentionExplanation {
  sentence: string | null; // the excerpt's sentence naming JFrog, when the excerpt has one
  how: string; // how the tag is set
  effect: string[]; // what the tag changed, from the item's own ranking and hold reasons
  modelNote: string | null; // the model's "why it matters", when it names JFrog
}

/** Why an item carries "Mentions JFrog", from fields the API already serves. The tag is a text match for "JFrog"
 *  over the title and the article text the system read; the article text itself is never served, so the sentence
 *  exists only when the excerpt (first 280 characters) holds it. */
export function mentionExplanation(d: {
  item: { title?: string | null; excerpt?: string | null; why_it_matters?: string | null; mentions_jfrog?: boolean; hold_reasons?: { code: string; held_at?: string[] }[] };
  ranking?: { raw_score?: number | null; adjustments?: unknown } | null;
}): MentionExplanation | null {
  const it = d.item;
  if (!it.mentions_jfrog) return null;
  const sentence = jfrogSentence(it.excerpt);
  const inTitle = /jfrog/i.test(it.title ?? "");
  const how = inTitle
    ? "The title names JFrog."
    : sentence
      ? "The article names JFrog; the sentence below is from its opening."
      : "A text match found the name JFrog in the article text the system read. That text isn't kept for display, only its first 280 characters, which don't include the mention.";
  const effect: string[] = [];
  const adj = Array.isArray(d.ranking?.adjustments) ? (d.ranking!.adjustments as unknown[]).map(String) : [];
  if (adj.some((a) => /mentions jfrog/i.test(a)) && typeof d.ranking?.raw_score === "number") {
    effect.push(`Score raised by 1 for mentioning JFrog (${d.ranking.raw_score} → ${d.ranking.raw_score + 1}).`);
  }
  const hold = (it.hold_reasons ?? []).find((h) => h.code === "mentions_jfrog");
  if (hold) effect.push(hold.held_at?.length === 3 ? "Held for an analyst at every autonomy level." : "Held for an analyst.");
  const modelNote = it.why_it_matters && /jfrog/i.test(it.why_it_matters) ? it.why_it_matters : null;
  return { sentence, how, effect, modelNote };
}
