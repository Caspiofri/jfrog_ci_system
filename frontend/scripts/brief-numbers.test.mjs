// npm test: the Brief's "Today in numbers" tiles (src/lib/briefNumbers.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { todayTiles } from "../src/lib/briefNumbers.ts";

// The live 1 Nov Brief: summary from GET /brief?date=2026-11-01, items from GET /run-metrics/20261101T0400Z-e9cae4.
const S = { brief_min_score: 3, published: 4, published_high: 1, published_below: 2, held: 11, held_high: 1,
  held_by_preliminary_score: { "5": 0, "4": 1, "3": 8, "<=2": 2, unscored: 0, noise: 0 }, level: "strict" };
const RUN = { collected: 239, kept: 26, new: 26, noise: 11 };
const byKey = (tiles) => Object.fromEntries(tiles.map((t) => [t.key, t]));

test("four tiles with short labels, in order", () => {
  assert.deepEqual(todayTiles(S, RUN).map((t) => t.label), ["Collected", "Published", "High score (4+)", "Needs review"]);
});

test("each number is the API's own field for that Brief", () => {
  const t = byKey(todayTiles(S, RUN));
  assert.equal(t.new.value, 26); // items.new of the 1 Nov run, not the 239 fetched
  assert.equal(t.new.value, RUN.new);
  assert.equal(t.published.value, S.published);
  assert.equal(t.high.value, S.published_high);
  assert.equal(t.review.value, S.held);
});

test("no count of low-score items", () => {
  const tiles = todayTiles(S, RUN);
  assert.ok(!tiles.some((t) => /low|below|score [12]\b/i.test(t.label)));
  assert.doesNotMatch(readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8"), /published_below/);
});

test("every tile explains what it counts on hover", () => {
  const t = byKey(todayTiles(S, RUN));
  for (const x of Object.values(t)) assert.ok(x.hint.length > 20, x.key);
  assert.match(t.published.hint, /scored 3 or higher/);
  assert.match(t.review.hint, /held at Strict/);
  assert.match(t.review.hint, /1 preliminarily scored 4–5/);
});

test("unscored held items are named in the Needs review hint", () => {
  const t = byKey(todayTiles({ ...S, held_by_preliminary_score: { ...S.held_by_preliminary_score, unscored: 2 } }, RUN));
  assert.match(t.review.hint, /2 not scored/);
});

test("no run record (older data, or a demo snapshot without it): new items unknown, not zero", () => {
  for (const run of [null, undefined, {}, { collected: 239 }]) {
    const t = byKey(todayTiles(S, run));
    assert.equal(t.new.value, null);
    assert.equal(t.new.hint, "Run metrics not recorded yet for this run.");
  }
});

test("the raw fetch count is never shown", () => {
  assert.ok(!todayTiles(S, RUN).some((t) => t.value === RUN.collected));
});

test("an empty window shows zeros, not blanks", () => {
  const t = byKey(todayTiles({ ...S, published: 0, published_high: 0, held: 0, held_high: 0 }, { new: 0 }));
  assert.deepEqual([t.new.value, t.published.value, t.high.value, t.review.value], [0, 0, 0, 0]);
});

test("the tiles are focusable for their hover (keyboard)", () => {
  const ci = readFileSync(new URL("../src/components/ci.tsx", import.meta.url), "utf8");
  assert.match(ci, /export function Hint[\s\S]*?tabIndex=\{0\}/);
});

import { runCountsFor } from "../src/lib/briefNumbers.ts";

test("two Brief days with different counts: each tile uses its own Brief's run", () => {
  const m1 = { run_id: "20261101T0400Z-e9cae4", items: { new: 26 } };
  const m2 = { run_id: "20261102T0400Z-bed018", items: { new: 13 } };
  const tile = (runId, m) => todayTiles(S, runCountsFor(runId, m))[0].value;
  assert.equal(tile("20261101T0400Z-e9cae4", m1), 26);
  assert.equal(tile("20261102T0400Z-bed018", m2), 13);
});

test("another run's metrics (kept from the previous Brief, or the request 404ed) never fill the tile", () => {
  const m1 = { run_id: "20261101T0400Z-e9cae4", items: { new: 26 } };
  assert.equal(runCountsFor("20261031T1345Z-802913", m1), null);
  const t = todayTiles(S, runCountsFor("20261031T1345Z-802913", m1))[0];
  assert.equal(t.value, null);
  assert.equal(t.hint, "Run metrics not recorded yet for this run.");
  assert.equal(runCountsFor("x", undefined), null);
});

test("the Brief asks for its own run with keepPreviousData off", () => {
  const src = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");
  assert.match(src, /\/run-metrics\/\$\{encodeURIComponent\(runId\)\}`\), \{ shouldRetryOnError: false, keepPreviousData: false \}/);
  assert.match(src, /todayTiles\(s, runCountsFor\(runId, run\.data\)\)/);
  assert.match(src, /runId=\{b\.window\.anchor_run_id\}/);
});

test("the Collected hover is the run's funnel; 1 Nov shows the run's values beside the values after analyst actions", () => {
  const row = { run_id: "R1", items: { collected: 239, kept: 26, new: 26, test_skip: 0, noise: 11, published: 3, held: 12 },
    items_after_actions: { published: 4, held: 11 }, reconstructed: null };
  assert.equal(byKey(todayTiles(S, runCountsFor("R1", row))).new.hint,
    "239 fetched → 26 new after removing duplicates → 11 removed as noise → 3 published · 12 need review at the end of the run · now 4 published · 11 need review after analyst actions");
});

test("a reconstructed row (30 Oct): test items set aside, empty published and held said as not recorded (never 0), the note", () => {
  const row = { run_id: "R0", items: { collected: 307, kept: 40, new: 40, test_skip: 26, noise: 5, published: null, held: null },
    items_after_actions: null, reconstructed: { decision: "D74", label: "Reconstructed from the item log", empty: { "items.published": "no routing" } } };
  const hint = byKey(todayTiles(S, runCountsFor("R0", row))).new.hint;
  assert.equal(hint, "307 fetched → 40 new after removing duplicates → 26 test items set aside, not sent to the model → 5 removed as noise → published and need review not recorded for this run · Reconstructed from the item log");
  assert.doesNotMatch(hint, /\b0 published|\b0 need review|4 published/);
});

test("a reconstructed row without a label still gets the note", () => {
  const row = { run_id: "R0", items: { new: 3, published: null, held: null }, reconstructed: { decision: "D74" } };
  assert.match(byKey(todayTiles(S, runCountsFor("R0", row))).new.hint, / · Reconstructed from the item log$/);
});

test("a funnel step whose field is empty is left out, never shown as 0", () => {
  assert.equal(byKey(todayTiles(S, { new: 13 })).new.hint, "13 new after removing duplicates → 4 published · 11 need review");
  assert.equal(byKey(todayTiles(S, { new: 13, collected: null, noise: undefined })).new.hint,
    "13 new after removing duplicates → 4 published · 11 need review");
  assert.equal(byKey(todayTiles(S, { new: 0, collected: 5, noise: 0 })).new.hint,
    "5 fetched → 0 new after removing duplicates → 0 removed as noise → 4 published · 11 need review");
});

test("the 30 Oct import Brief is tagged with what it covers", () => {
  const src = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");
  assert.match(src, />Initial import: previous 14 days<\/Tag>/);
  assert.doesNotMatch(src, /Initial import \(backfill\)/);
});

test("a row a run wrote itself carries no reconstructed note", () => {
  const row = { run_id: "R1", items: { new: 26, published: 3, held: 12 }, reconstructed: null };
  assert.doesNotMatch(byKey(todayTiles(S, runCountsFor("R1", row))).new.hint, /Reconstructed/);
});
