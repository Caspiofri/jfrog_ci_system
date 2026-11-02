// npm test: the header above the competitor cards: what they count (published only; awaiting review on the tag).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("../src/app/competitors/page.tsx", import.meta.url), "utf8");

test("header above the cards: title and window; no totals line; the (i) says the big number is published only", () => {
  assert.match(page, /Published competitor items <span[^>]*>· found \{fmtDate\(d\.week\.start\)\}–\{fmtDate\(d\.week\.end\)\}/);
  assert.doesNotMatch(page, /cardTotals|across the six competitors/);
  assert.match(page, /const CARDS_EXPLAIN = "Only published articles\.";/);
  assert.match(page, /<InfoHint text=\{CARDS_EXPLAIN\} label="What the cards count" \/>/);
  assert.doesNotMatch(page, /All published and awaiting-review items/);
  assert.ok(page.indexOf("data-cards-header") < page.indexOf("<CompetitorCardView"), "above the cards");
});
test("the page's (i) says what the page is: JFrog's competitors and how they compare with JFrog; top score explained on its badge", () => {
  assert.match(page, /<PageHead title="Competitors" info=\{PAGE_INFO\} \/>/);
  assert.match(page, /PAGE_INFO =\s*"JFrog's tracked competitors and how they compare with JFrog: what each one's public pages state on the 7 JFrog capabilities/);
  assert.doesNotMatch(page, /info="Top score is the highest score/);
  const parts = readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8");
  assert.match(parts, /top score <ScoreBadge score=\{c\.threat\} title="Top score: the highest score of any of this competitor's items this week" \/>/);
});
