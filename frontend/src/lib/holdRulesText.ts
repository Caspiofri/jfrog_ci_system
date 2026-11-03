// The (i) next to "What needs my decision?" in the Review queue: the routing rules in plain words, from DOC's
// routing-rules document as Ofri gave it (3 Nov); Mentions JFrog reworded by Ofri at review. Explanations kept verbatim. Keyed by hold-reason code: the name shown
// is the chip's own label (HOLD_LABEL in format.ts), so each reason has one name across the app. No imports, so `npm test` runs it.

export const HOLD_RULES_INTRO =
  "These items were held back from the Brief for you to approve, edit, dismiss or flag. An item is held for each reason below that applies at your autonomy level (Strict, Balanced or Relaxed).";

/** [hold-reason code, explanation]; the page shows HOLD_LABEL[code] before each explanation. */
export const HOLD_RULES: [string, string][] = [
  ["unvetted_source", "the publisher isn't on our vetted list yet."],
  ["low_confidence", "the AI was less than 80% sure how to label it."],
  ["teaser_high_score", "it scored 4+ from a short teaser, not the full article."],
  ["junk_extraction", "it scored 4+, but the page text we got looked broken."],
  ["pricing", "pricing or packaging news is always checked by a person."],
  ["m_and_a", "funding, acquisitions and partnerships are always checked by a person."],
  ["mentions_jfrog", "anything that names JFrog or one of its products is always checked by a person."],
  ["model_failure", "the AI gave no usable answer for this item."],
  ["invalid_output", "the AI's answer broke our format rules, so it wasn't trusted."],
  ["changed_cell", "a JFrog-vs-competitor comparison value changed and needs confirming."],
];
