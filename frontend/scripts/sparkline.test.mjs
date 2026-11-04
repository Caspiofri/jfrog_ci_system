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

test("in every card, from the profile's activity, the Brief date from the API; D112 card order", () => {
  const spark = readFileSync(new URL("../src/components/competitors/Sparkline.tsx", import.meta.url), "utf8");
  assert.match(spark, /useRecord<CompetitorProfile>\(`\/api\/v1\/competitors\/\$\{encodeURIComponent\(k\)\}`/);
  assert.match(spark, /lastDays\(a\.series, q\.data\.date\)/);
  assert.match(spark, /<Tooltip content=\{<Tip \/>\}/);
  assert.doesNotMatch(spark, /trend|delta|score|percent/i);
  const parts = readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8");
  // D112 order: name and top-score badge; awaiting review and mentions JFrog; sparkline; top item
  const card = parts.slice(parts.indexOf("export function CompetitorCardView"), parts.indexOf("export function DealsTable"));
  const at = (s) => card.indexOf(s);
  assert.ok(at("data-top-score") < at("data-card-tags") && at("data-card-tags") < at("<CardSparkline") && at("<CardSparkline") < at("data-top-item"));
  assert.match(card, /awaiting review[\s\S]*mention JFrog/);
  assert.doesNotMatch(card, /<Trend|<MixBar|items_7d|items_today|tracked_changes|head_to_head_changes/);
  assert.match(card, /c\.top_item\.score[\s\S]*c\.top_item\.published_at/);
  assert.doesNotMatch(spark, /SPARK_CAPTION/); // the caption is once above the cards
  // straight segments between days, never a smoothed curve
  assert.match(spark, /<Line type="linear" dataKey="items"/);
  assert.doesNotMatch(spark, /monotone|natural|basis|cardinal|step/);
});

test("cards: sparkline and top item sit at the bottom; the top item is exactly 3 lines, title cut with … and in full on hover", () => {
  const parts = readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8");
  const card = parts.slice(parts.indexOf("export function CompetitorCardView"), parts.indexOf("export function DealsTable"));
  assert.match(card, /<div className="mt-auto flex flex-col gap-2\.5" data-card-bottom>\s*<CardSparkline k=\{c\.key\} \/>/);
  assert.match(card, /data-top-item>/);
  assert.match(card, /<p className="m-0 line-clamp-2 h-8" title=\{c\.top_item\.title\}>/);
  assert.match(card, /<p className="m-0 h-4 truncate text-mute" data-top-item-meta>[\s\S]*?c\.top_item\.score[\s\S]*?c\.top_item\.published_at/);
  assert.match(card, /<p className="m-0 h-12 text-mute">No cleared items this week\.<\/p>/);
  assert.match(card, /text-xs leading-4/);
});

test("profile: no 'vs previous 7 days' (D112, same reason as the cards)", () => {
  const profile = readFileSync(new URL("../src/app/competitors/[key]/page.tsx", import.meta.url), "utf8");
  const parts = readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(profile, /<Trend|previous 7 days|items_prev_7d/);
  assert.doesNotMatch(parts, /function Trend|vs previous 7 days/);
  assert.match(profile, /<KpiTile value=\{c\.items_7d\} label="Cleared in 7 days" \/>/);
});
