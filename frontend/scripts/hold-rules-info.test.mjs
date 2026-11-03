// npm test: the (i) next to "What needs my decision?" carries Ofri's routing-rules explanations as written, each
// under the same name its chip uses (HOLD_LABEL in src/lib/format.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { HOLD_LABEL } from "../src/lib/format.ts";
import { HOLD_RULES, HOLD_RULES_INTRO } from "../src/lib/holdRulesText.ts";

const AS_SHOWN = `These items were held back from the Brief for you to approve, edit, dismiss or flag. An item is held for each reason below that applies at your autonomy level (Strict, Balanced or Relaxed).

- Unvetted source: the publisher isn't on our vetted list yet.
- Low confidence: the AI was less than 80% sure how to label it.
- High score on a teaser: it scored 4+ from a short teaser, not the full article.
- Junk extraction: it scored 4+, but the page text we got looked broken.
- Pricing: pricing or packaging news is always checked by a person.
- M&A / funding: funding, acquisitions and partnerships are always checked by a person.
- Mentions JFrog: anything that names JFrog or one of its products is always checked by a person.
- Model failure: the AI gave no usable answer for this item.
- Invalid model output: the AI's answer broke our format rules, so it wasn't trusted.
- Changed head-to-head cell: a JFrog-vs-competitor comparison value changed and needs confirming.`;

test("the text is exactly as shown: chip names, explanations as given", () => {
  assert.equal([HOLD_RULES_INTRO, "", ...HOLD_RULES.map(([code, v]) => `- ${HOLD_LABEL[code]}: ${v}`)].join("\n"), AS_SHOWN);
});

test("one entry per chip reason, in the chips' order, none missing or extra", () => {
  assert.deepEqual(HOLD_RULES.map(([code]) => code), Object.keys(HOLD_LABEL));
});

test("the (i) sits on the \"What needs my decision?\" panel and names each reason with the chip label", () => {
  const src = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");
  assert.match(src, /title="What needs my decision\?"\s+info=\{<HoldRulesInfo \/>\}/);
  assert.match(src, /function HoldRulesInfo\(\)[\s\S]*?HOLD_RULES_INTRO[\s\S]*?HOLD_RULES\.map\(\(\[code, v\]\)[\s\S]*?label\(HOLD_LABEL, code\)/);
});
