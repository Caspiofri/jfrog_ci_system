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

test("overview: importance colours and the cards' category bar have a visible legend", () => {
  assert.match(overview, /<ColourLegends \/>/);
  assert.match(parts, /<MixBar mix=\{c\.category_mix\} \/>/, "the cards use the category bar");
});

test("profile: score colours, the category bar, the activity chart and the head-to-head highlight have legends", () => {
  assert.match(profile, /<ColourLegends \/>/);
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

test("every item view shows both legends, Importance (1–5) and Category, outside any hover", () => {
  for (const f of ["app/review/page.tsx", "app/log/page.tsx", "app/competitors/page.tsx", "app/competitors/[key]/page.tsx"]) {
    assert.match(read(f), /<ColourLegends\b[^>]*\/>/, f);
  }
  const fn = ci.slice(ci.indexOf("export function ColourLegends"), ci.indexOf("/** \"n=12\""));
  assert.match(fn, /title="Importance \(1–5\)"/);
  assert.match(fn, /title="Category" categories=\{Object\.keys\(CATEGORY_COLOR\)\}/);
  assert.doesNotMatch(fn, /Hint|Tooltip/);
});

test("the Log's legend also names noise (N) and not scored (–)", () => {
  assert.match(read("app/log/page.tsx"), /<ColourLegends unscored \/>/);
  assert.match(ci, /text: "N", label: "noise"/);
  assert.match(ci, /text: "–", label: "not scored"/);
});

test("Brief: Importance (1–5) once, directly under the title; under the insights only the Category colours", () => {
  const brief = read("app/brief/page.tsx");
  assert.equal((brief.match(/<ImportanceLegend\b/g) ?? []).length, 1);
  assert.equal((brief.match(/<CategoryColours\b/g) ?? []).length, 1);
  assert.doesNotMatch(brief, /<ColourLegends\b|<ScoreLegend\b|<CategoryLegend\b|<ColorLegend\b/);
  assert.match(brief, /<PageHead[\s\S]*?\/>\s*<ImportanceLegend /);
  assert.match(brief, /<InsightsPanel [^\n]*\/>\s*<CategoryColours /);
  assert.match(ci, /export function ImportanceLegend[\s\S]*?title="Importance \(1–5\)"/);
  assert.match(ci, /export function CategoryColours[\s\S]*?title="Category"/);
});
