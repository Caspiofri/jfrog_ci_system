// The (i) next to "What needs my decision?" in the Review queue: the routing rules in plain words, from DOC's
// routing-rules document as Ofri gave it (3 Nov). Kept verbatim. No imports, so `npm test` runs it.

export const HOLD_RULES_INTRO =
  "These items were held back from the Brief for you to approve, edit, dismiss or flag. An item is held for each reason below that applies at your autonomy level (Strict, Balanced or Relaxed).";

export const HOLD_RULES: [string, string][] = [
  ["Unvetted source", "the publisher isn't on our vetted list yet."],
  ["Low confidence", "the AI was less than 80% sure how to label it."],
  ["High score, teaser only", "it scored 4+ from a short teaser, not the full article."],
  ["High score, bad page text", "it scored 4+, but the page text we got looked broken."],
  ["Pricing", "pricing or packaging news is always checked by a person."],
  ["Funding / M&A", "funding, acquisitions and partnerships are always checked by a person."],
  ["Mentions JFrog", "anything that names JFrog is always checked by a person."],
  ["Model failure", "the AI gave no usable answer for this item."],
  ["Invalid output", "the AI's answer broke our format rules, so it wasn't trusted."],
  ["Changed comparison", "a JFrog-vs-competitor comparison value changed and needs confirming."],
];
