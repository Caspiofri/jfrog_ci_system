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

// "Where JFrog is mentioned" (D77): Item.jfrog_mention, a read-only API field. A mention, not a comparison.
export const MENTION_TITLE = "Where JFrog is mentioned";
export const MENTION_NOTE = "A mention of JFrog in the article, not a comparison.";
export const NOT_IN_STORED_TEXT =
  "JFrog is named on the article page, but not in the part of the article we store, so no passage can be shown.";

/** The text cut into pieces, each "JFrog" (any letter case) marked, for React to render as plain text nodes (D113).
 *  Joining every piece's text gives the input back unchanged. */
export function splitJfrog(text: string): { text: string; jfrog: boolean }[] {
  return text.split(/(jfrog)/i).filter((t) => t !== "").map((t) => ({ text: t, jfrog: /^jfrog$/i.test(t) }));
}

export interface JfrogMentionLike { status?: string; snippet?: string | null; found_in?: string | null }
export type MentionSection = { kind: "found"; snippet: string; inTitle: boolean } | { kind: "not_in_stored_text" };

/** What the section shows; null when the API sent no mention (an older snapshot) or a status it doesn't know. */
export function mentionSection(m: JfrogMentionLike | null | undefined): MentionSection | null {
  if (m?.status === "found" && m.snippet?.trim()) return { kind: "found", snippet: m.snippet, inTitle: m.found_in === "title" };
  if (m?.status === "not_in_stored_text") return { kind: "not_in_stored_text" };
  return null;
}

export function mentionHint(excerpt: string | null | undefined, mention?: JfrogMentionLike | null): string {
  const sec = mentionSection(mention);
  if (sec?.kind === "found") return `Mentioned: “${sec.snippet}”`;
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
