// npm test: the insight header shows no story count (the evidence dropdown already lists the stories).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const src = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");
const card = src.slice(src.indexOf("function InsightCard("), src.indexOf("function useCitedItem("));
const header = card.slice(card.indexOf("data-insight-header"), card.indexOf("<h3"));

test("the insight header has no story or item count", () => {
  assert.ok(header.length > 0, "header found");
  assert.doesNotMatch(header, /story_ids|item_ids|stories|"story"/);
});

test("the evidence dropdown is still there", () => {
  assert.match(card, /Show evidence/);
  assert.match(card, /ClaimBlock/);
});

const details = card.slice(card.indexOf("data-insight-details"));
const collapsed = card.slice(card.indexOf("return ("), card.indexOf("{details ? ("));

test("collapsed by default: only the chips and the title are shown", () => {
  assert.match(card, /const \[details, setDetails\] = useState\(false\)/);
  assert.match(collapsed, /<Tag>\{label\(PATTERN_LABEL, ins\.pattern\)\}<\/Tag>/);
  assert.match(collapsed, /<ContinuityBadge c=\{ins\.continuity\} \/>/);
  assert.match(collapsed, /<ExperimentalChip small \/>/);
  assert.match(collapsed, /\{ins\.title\}/);
  for (const hidden of ["ins.summary", "ins.why_it_matters", "Show evidence", "ins.max_score"]) {
    assert.ok(!collapsed.includes(hidden), `${hidden} is visible while collapsed`);
  }
});

test("a click opens the details: summary and why it matters; keyboard via the title button", () => {
  assert.match(card, /onClick=\{toggle\}/);
  assert.match(card, /<button type="button" aria-expanded=\{details\}[^>]*onClick=\{\(e\) => \{ e\.stopPropagation\(\); toggle\(\); \}\}/);
  assert.match(details, /\{ins\.summary\}/);
  assert.match(details, /Why it matters: /);
});

test("the claims stay in their own dropdown inside the details, closed until clicked", () => {
  assert.match(card, /const \[open, setOpen\] = useState\(false\)/);
  assert.match(details, /aria-expanded=\{open\}[\s\S]*?Show evidence[\s\S]*?\{open \? \([\s\S]*?<ClaimBlock/);
});
