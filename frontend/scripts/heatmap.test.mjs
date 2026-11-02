// npm test: "Where competitors are active" (src/lib/heatmap.ts, components/competitors/Heatmap.tsx).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { KEPT_STATUSES, buildHeatmap, heatColor, heatmapQuery, legendSteps } from "../src/lib/heatmap.ts";

const NOW = "2026-11-01T04:04:04Z";
const COMPS = ["cloudsmith", "sonatype", "github", "gitlab", "snyk", "aws"];
const CATS = ["Product & Features", "Pricing & Packaging", "AI & Agents", "Security", "Funding/M&A/Partnerships", "Customers & Market", "Leadership & Org"];
let n = 0;
const row = (o) => ({ item_id: `i${++n}`, run_id: "r", title: "t", url: "https://x.test/a", source: "s", publisher: "p", competitor: "github",
  category: "AI & Agents", score: 3, published_at: "2026-10-30T10:00:00Z", collected_at: "2026-10-30T12:00:00Z", discovered_at: null,
  status: "auto_published", stage: "route", reason: "", duplicate_of: null, text_status: null, ...o });

test("counts per competitor and category; one count per item even when the Log lists it twice", () => {
  const a = row({});
  const hm = buildHeatmap([a, { ...a, run_id: "r2" }, row({}), row({ competitor: "gitlab", category: "Security" })], COMPS, CATS, NOW);
  assert.equal(hm.cells.github["AI & Agents"].count, 2);
  assert.equal(hm.cells.gitlab.Security.count, 1);
  assert.equal(hm.cells.aws.Security.count, 0);
  assert.equal(hm.total, 3);
});

test("noise and dismissed items, Industry and uncategorised rows are not counted", () => {
  const hm = buildHeatmap([
    row({ status: "dropped", stage: "classify" }), row({ status: "dismissed" }), row({ status: "held_out" }),
    row({ competitor: "industry" }), row({ category: null }), row({ status: "awaiting_review" }), row({ status: "approved" }),
  ], COMPS, CATS, NOW);
  assert.equal(hm.total, 2);
  assert.deepEqual(KEPT_STATUSES, ["auto_published", "awaiting_review", "approved"]);
});

test("window: published in the last 7 days by feed date, up to the API's now", () => {
  const hm = buildHeatmap([
    row({ published_at: "2026-10-25T04:04:05Z" }), // just inside
    row({ published_at: "2026-10-25T04:04:04Z" }), // exactly 7 days: out
    row({ published_at: "2026-11-01T04:04:05Z" }), // after now: out
    row({ published_at: null }),
  ], COMPS, CATS, NOW);
  assert.equal(hm.total, 1);
});

test("no ring: cells carry only their count and items", () => {
  const comp = readFileSync(new URL("../src/components/competitors/Heatmap.tsx", import.meta.url), "utf8");
  const hm = buildHeatmap([row({}), row({ category: "Security" })], COMPS, CATS, NOW);
  assert.deepEqual(Object.keys(hm.cells.github["AI & Agents"]).sort(), ["count", "items"]);
  assert.equal(hm.max, 1);
  assert.doesNotMatch(comp, /ring-\[#f59e0b\]|Ring =|most active category|data-ring/);
});

test("empty state: no items at all", () => {
  const hm = buildHeatmap([], COMPS, CATS, NOW);
  assert.equal(hm.total, 0);
  assert.equal(hm.max, 0);
  assert.deepEqual(legendSteps(0), []);
});

test("colour: one scale, light to strong; 0 is the empty light cell", () => {
  const zero = heatColor(0, 10), low = heatColor(1, 10), high = heatColor(10, 10);
  assert.equal(zero.bg, "#f6f8fb");
  const alpha = (c) => Number(c.bg.match(/, ([\d.]+)\)$/)[1]);
  assert.ok(alpha(low) < alpha(high));
  assert.equal(high.bg.slice(0, 18), low.bg.slice(0, 18), "same hue");
  assert.deepEqual(legendSteps(29), [1, 15, 29]);
});

test("query: one Log call filtered by kept status, the six competitors and the first day", () => {
  const q = heatmapQuery(COMPS, NOW);
  assert.deepEqual(q.status, KEPT_STATUSES);
  assert.deepEqual(q.competitor, COMPS);
  assert.equal(q.date_from, "2026-10-25");
  assert.equal(q.limit, 200);
});

const comp = readFileSync(new URL("../src/components/competitors/Heatmap.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../src/app/competitors/page.tsx", import.meta.url), "utf8");

test("title, caption, legend with the scale; directly under the matrix", () => {
  assert.match(comp, /<Panel title="Where competitors are active">/);
  assert.match(comp, /HEATMAP_CAPTION = "Activity by category, from automatic classification\. Last 7 days\."/);
  assert.match(comp, /legendSteps\(hm\.max\)/);
  assert.match(page, /<CapabilityMatrix \/>\s*<ActivityHeatmap \/>/);
});

test("columns: the six tracked competitors with avatars, as the matrix; rows: the Category legend's order", () => {
  assert.match(comp, /!c\.is_industry && c\.key !== "industry"\)\.slice\(0, 6\)/);
  assert.match(comp, /<CompetitorAvatar k=\{k\}/);
  assert.match(comp, /const cats = Object\.keys\(CATEGORY_COLOR\)/);
});

test("a click lists the cell's items; the title opens the drawer", () => {
  assert.match(comp, /onClick=\{\(\) => setSel/);
  assert.match(comp, /<ItemTitle title=\{r\.title\} url=\{r\.url\} onOpen=\{\(\) => drawer\.open\(r\.item_id!\)\} \/>/);
});

test("no gap, threat, ahead or behind", () => {
  const visible = (s) => s.replace(/\/\/.*|\/\*[\s\S]*?\*\//g, "").replace(/className=("[^"]*"|\{[^}]*\})/g, "");
  for (const s of [comp, readFileSync(new URL("../src/lib/heatmap.ts", import.meta.url), "utf8")]) {
    assert.doesNotMatch(visible(s), /\b(gap|threat|ahead|behind)\b/i);
  }
});

test("the heatmap ends where the competitor cards end (the latest Brief's run), never at today's date", () => {
  assert.match(comp, /const cards = useApi<Competitors>\("\/api\/v1\/competitors"\);\s*const now = cards\.data\?\.week\?\.end;/);
  assert.doesNotMatch(comp + readFileSync(new URL("../src/lib/heatmap.ts", import.meta.url), "utf8"), /new Date\(\)|Date\.now\(\)/);
});

test("each count says what it counts: the heatmap by feed date (published or awaiting review), the cards by the date found", () => {
  assert.match(comp, /HEATMAP_COUNTS = "Counts items by feed date, published or awaiting review\. The competitor cards count published items by the date they were found\."/);
  assert.match(comp, /data-counts>\{HEATMAP_COUNTS\}/);
  const parts = readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8");
  assert.match(parts, /published, found in the last 7 days · \{c\.items_today\} in this Brief/);
});
