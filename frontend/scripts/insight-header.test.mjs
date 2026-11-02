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
