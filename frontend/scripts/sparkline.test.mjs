// npm test: D93/D94, the 14-day line in each competitor card, from GET /competitors/{key} activity. No new measure.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { SPARK_CAPTION, SPARK_DAYS, SPARK_TITLE, lastDays } from "../src/lib/sparkline.ts";

test("title and caption as written", () => {
  assert.equal(SPARK_TITLE, "Cleared Items per Day · Last 14 Days");
  assert.equal(SPARK_CAPTION, "By article date. Items that passed routing or were approved.");
  assert.equal(SPARK_DAYS, 14);
});

test("14 days ending on the Brief date, oldest first; a day the API didn't list is 0", () => {
  const series = [{ date: "2026-10-18", items: 9 }, { date: "2026-10-19", items: 2 }, { date: "2026-10-28", items: 32 }, { date: "2026-11-01", items: 1 }];
  const r = lastDays(series, "2026-11-01");
  assert.equal(r.length, 14);
  assert.equal(r[0].date, "2026-10-19");
  assert.equal(r[13].date, "2026-11-01");
  assert.deepEqual(r.map((x) => x.items), [2, 0, 0, 0, 0, 0, 0, 0, 0, 32, 0, 0, 0, 1]); // 18 Oct falls outside
  assert.deepEqual(lastDays(series, "not a date"), []);
});

test("in every card, from the profile's activity, the Brief date from the API; card numbers untouched", () => {
  const spark = readFileSync(new URL("../src/components/competitors/Sparkline.tsx", import.meta.url), "utf8");
  assert.match(spark, /useRecord<CompetitorProfile>\(`\/api\/v1\/competitors\/\$\{encodeURIComponent\(k\)\}`/);
  assert.match(spark, /lastDays\(a\.series, q\.data\.date\)/);
  assert.match(spark, /<Tooltip content=\{<Tip \/>\}/);
  assert.doesNotMatch(spark, /trend|delta|score|percent/i);
  const parts = readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8");
  // order: trend line, then the sparkline, then the category mix bar
  assert.match(parts, /<Trend t=\{c\.trend\} prev=\{c\.items_prev_7d\} \/>\s*<CardSparkline k=\{c\.key\} \/>\s*<MixBar mix=\{c\.category_mix\} \/>/);
  // straight segments between days, never a smoothed curve
  assert.match(spark, /<Line type="linear" dataKey="items"/);
  assert.doesNotMatch(spark, /monotone|natural|basis|cardinal|step/);
  assert.match(parts, /\{c\.items_7d\}<\/b>/);
});
