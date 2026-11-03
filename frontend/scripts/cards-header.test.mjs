// npm test: the header above the competitor cards: what they count (published only; awaiting review on the tag).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("../src/app/competitors/page.tsx", import.meta.url), "utf8");

test("header above the cards: title and window; no totals line; the (i) says the big number is published only", () => {
  // D89: title "Weekly", the API's week on a line under it
  assert.match(page, /<h2[^>]*>\s*Weekly\s*<InfoHint[^>]*\/>\s*<\/h2>\s*<p[^>]*data-week-range>\{fmtDate\(d\.week\.start\)\}–\{fmtDate\(d\.week\.end\)\}<\/p>/);
  assert.doesNotMatch(page, /Published competitor items/);
  assert.doesNotMatch(page, /cardTotals|across the six competitors/);
  assert.match(page, /const CARDS_EXPLAIN = "Only cleared items \(passed routing, or approved by an analyst\)\. Click a card for the competitor's full details\.";/);
  assert.match(page, /<InfoHint text=\{CARDS_EXPLAIN\} label="What the cards count" \/>/);
  assert.doesNotMatch(page, /All published and awaiting-review items/);
  assert.ok(page.indexOf("data-cards-header") < page.indexOf("<CompetitorCardView"), "above the cards");
});
test("the page's (i) says what the page is: JFrog's competitors and how they compare with JFrog; top score explained on its badge", () => {
  assert.match(page, /<PageHead title="Competitors" info=\{PAGE_INFO\} \/>/);
  assert.match(page, /PAGE_INFO =\s*"JFrog's tracked competitors and how they compare with JFrog: what each one's public pages state on the 7 JFrog capabilities/);
  assert.doesNotMatch(page, /info="Top score is the highest score/);
  const parts = readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8");
  // the card shows the score badge; "Top score this week" is its hover and keyboard-focus text, not visible text
  assert.match(parts, /<Hint text=\{TOP_SCORE_LABEL\} className="[^"]*">\s*<span className="sr-only">\{TOP_SCORE_LABEL\}: <\/span>\s*<span data-top-score><ScoreBadge score=\{c\.threat\} \/><\/span>\s*<\/Hint>/);
  assert.doesNotMatch(parts, />\s*Top score this week <ScoreBadge/);
});

test("D96 follow-up: the page's (i) says what the heatmap counts (cleared items by date collected), not \"active\"", () => {
  assert.match(page, /their cleared items by category, counted by the date collected this week/);
  assert.doesNotMatch(page, /where they were active/);
  const profile = readFileSync(new URL("../src/app/competitors/[key]/page.tsx", import.meta.url), "utf8");
  assert.match(profile, /How active are they\?/); // by article date: kept
  assert.match(profile, /last activity/);
});
