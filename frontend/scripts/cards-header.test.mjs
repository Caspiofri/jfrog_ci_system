// npm test: the header above the competitor cards: what they count, with totals (src/lib/cardTotals.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { cardTotals } from "../src/lib/cardTotals.ts";

// GET /competitors on the 1 Nov demo: [key, items_7d, pending_review]
const CARDS = [["cloudsmith", 9, 1], ["sonatype", 5, 0], ["github", 73, 17], ["gitlab", 17, 25], ["snyk", 14, 2], ["aws", 9, 4], ["industry", 19, 59]]
  .map(([key, items_7d, pending_review]) => ({ key, items_7d, pending_review, is_industry: key === "industry" }));

test("totals sum the six competitors' cards; Industry is not a competitor", () => {
  assert.deepEqual(cardTotals(CARDS), { published: 127, queued: 49 });
  assert.deepEqual(cardTotals([]), { published: 0, queued: 0 });
});

const page = readFileSync(new URL("../src/app/competitors/page.tsx", import.meta.url), "utf8");

test("a clear header above the cards: title, the window, totals; the explanation in the (i) hint", () => {
  assert.match(page, /Published competitor items <span[^>]*>· found \{fmtDate\(d\.week\.start\)\}–\{fmtDate\(d\.week\.end\)\}/);
  assert.match(page, /\{cardTotals\(d\.items\)\.published\}<\/b> published/);
  assert.match(page, /\{cardTotals\(d\.items\)\.queued\}<\/b> awaiting review/);
  assert.match(page, /CARDS_EXPLAIN =\s*"All published and awaiting-review items per competitor, found in the last 7 days\. Noise and dismissed items are left out; Industry is market news with no tracked competitor\.";/);
  assert.match(page, /<InfoHint text=\{`\$\{CARDS_EXPLAIN\} Queue level: \$\{label\(LEVEL_LABEL, d\.level\)\}\.`\} label="What the cards count" \/>/);
  assert.doesNotMatch(page, /data-cards-explain/);
  assert.ok(page.indexOf("data-cards-header") < page.indexOf("<CompetitorCardView"), "above the cards");
  assert.doesNotMatch(page, /counted by discovery time; published items only/);
});
