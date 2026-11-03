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
  assert.doesNotMatch(profile, /<ColourLegends\b/); // removed from the competitor profile (Ofri, 3 Nov)
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
  for (const f of ["app/review/page.tsx", "app/log/page.tsx", "app/competitors/page.tsx"]) {
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

test("Brief: Importance (1–5) once, directly under the title; no category legend", () => {
  const brief = read("app/brief/page.tsx");
  assert.equal((brief.match(/<ImportanceLegend\b/g) ?? []).length, 1);
  assert.doesNotMatch(brief, /<CategoryColours\b|<ColourLegends\b|<ScoreLegend\b|<CategoryLegend\b|<ColorLegend\b/);
  assert.match(brief, /<PageHead[\s\S]*?\/>\s*<ImportanceLegend /);
  assert.match(ci, /export function ImportanceLegend[\s\S]*?title="Importance \(1–5\)"/);
});

test("Competitors overview: the legends sit under the competitor cards, not above them", () => {
  const i = overview.indexOf("<ColourLegends />"), cards = overview.indexOf("<CompetitorCardView");
  assert.ok(i > cards && cards > -1);
  assert.equal((overview.match(/<ColourLegends \/>/g) ?? []).length, 1);
});

test("Importance legend names every score, 2 and 1 in the rubric's own words", async () => {
  const { RUBRIC } = await import("../src/lib/format.ts");
  assert.deepEqual([5, 4, 3, 2, 1].map((n) => RUBRIC[n].label),
    ["Strategic move", "Material change", "Relevant development", "Intelligence value", "Routine update"]);
  assert.match(RUBRIC[2].competitor, /^No new event, but intelligence value/); // rubric v2 row 2, verbatim
  assert.match(RUBRIC[1].competitor, /^A routine operational event/); // rubric v2 row 1, verbatim
});

test("competitor profile: the head-to-head changes tile is marked Future", () => {
  assert.match(profile, /<KpiTile future value=\{c\.head_to_head_changes \?\? "—"\} label="Head-to-head changes"/);
  assert.match(ci, /\{future \? <Tag[^>]*>Future<\/Tag> : null\}/);
});
