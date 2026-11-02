// npm test: every competitor view that uses colour shows a visible legend; no colour meaning lives only in a hover.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const overview = read("app/competitors/page.tsx");
const profile = read("app/competitors/[key]/page.tsx");
const parts = read("components/competitors/parts.tsx");
const h2h = read("components/competitors/HeadToHead.tsx");
const chart = read("components/competitors/ActivityChart.tsx");
const ci = read("components/ci.tsx");

test("overview: threat colours and the cards' category bar have a visible legend", () => {
  assert.match(overview, /<ScoreLegend\b/);
  assert.match(overview, /<CategoryLegend\b/);
  assert.match(parts, /<MixBar mix=\{c\.category_mix\} \/>/, "the cards use the category bar");
});

test("profile: score colours, the category bar, the activity chart and the head-to-head highlight have legends", () => {
  assert.match(profile, /<ScoreLegend\b/);
  assert.match(profile, /<MixBar mix=\{c\.category_mix\} legend \/>/);
  assert.match(chart, /a day with an item rated 4 or 5/);
  assert.match(h2h, /<ColorLegend[^>]*Highlighted row: changed this week/);
});

test("the head-to-head highlight is explained on screen, not only in the hint", () => {
  assert.match(profile, /info="Changed cells are highlighted/);
  assert.match(h2h, /changed this week/);
});

test("the legend names each colour in text, and score legend uses the rubric's own labels only", () => {
  assert.match(ci, /export function ColorLegend[\s\S]*?\{it\.label\}/);
  assert.match(ci, /RUBRIC\[n\]\?\.label \?\? null/);
});
