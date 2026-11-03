// npm test: the (i) next to "What needs my decision?" carries Ofri's routing-rules text as written.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { HOLD_RULES, HOLD_RULES_INTRO } from "../src/lib/holdRulesText.ts";

const AS_GIVEN = `These items were held back from the Brief for you to approve, edit, dismiss or flag. An item is held for each reason below that applies at your autonomy level (Strict, Balanced or Relaxed).

- Unvetted source: the publisher isn't on our vetted list yet.
- Low confidence: the AI was less than 80% sure how to label it.
- High score, teaser only: it scored 4+ from a short teaser, not the full article.
- High score, bad page text: it scored 4+, but the page text we got looked broken.
- Pricing: pricing or packaging news is always checked by a person.
- Funding / M&A: funding, acquisitions and partnerships are always checked by a person.
- Mentions JFrog: anything that names JFrog is always checked by a person.
- Model failure: the AI gave no usable answer for this item.
- Invalid output: the AI's answer broke our format rules, so it wasn't trusted.
- Changed comparison: a JFrog-vs-competitor comparison value changed and needs confirming.`;

test("the text is exactly as given", () => {
  assert.equal([HOLD_RULES_INTRO, "", ...HOLD_RULES.map(([k, v]) => `- ${k}: ${v}`)].join("\n"), AS_GIVEN);
});

test("the (i) sits on the \"What needs my decision?\" panel and renders the intro and the list", () => {
  const src = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");
  assert.match(src, /title="What needs my decision\?"\s+info=\{<HoldRulesInfo \/>\}/);
  assert.match(src, /function HoldRulesInfo\(\)[\s\S]*?HOLD_RULES_INTRO[\s\S]*?HOLD_RULES\.map/);
});
