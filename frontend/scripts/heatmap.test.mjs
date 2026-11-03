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
  category: "AI & Agents", score: 3, published_at: "2026-10-30T10:00:00Z", collected_at: "2026-10-30T12:00:00Z", discovered_at: "2026-10-30T12:00:00Z",
  status: "auto_published", stage: "route", reason: "", duplicate_of: null, text_status: null, ...o });

test("counts per competitor and category; one count per item even when the Log lists it twice", () => {
  const a = row({});
  const hm = buildHeatmap([a, { ...a, run_id: "r2" }, row({}), row({ competitor: "gitlab", category: "Security" })], COMPS, CATS, NOW);
  assert.equal(hm.cells.github["AI & Agents"].count, 2);
  assert.equal(hm.cells.gitlab.Security.count, 1);
  assert.equal(hm.cells.aws.Security.count, 0);
  assert.equal(hm.total, 3);
});

test("counted as the card's number: published (incl. approved and flagged); awaiting review, noise, dismissed, Industry not", () => {
  const hm = buildHeatmap([
    row({ status: "dropped", stage: "classify" }), row({ status: "dismissed" }), row({ status: "held_out" }), row({ status: "awaiting_review" }),
    row({ competitor: "industry" }), row({ category: null }), row({ status: "approved" }), row({ status: "flagged" }),
  ], COMPS, CATS, NOW);
  assert.equal(hm.total, 2);
  assert.equal(hm.colTotals.github, 2);
  assert.deepEqual(KEPT_STATUSES, ["auto_published", "approved", "flagged"]);
});
test("window: by the date found, the cards' 7 days (start exclusive, end inclusive); the feed date doesn't matter", () => {
  const hm = buildHeatmap([
    row({ discovered_at: "2026-10-25T04:04:05Z", published_at: "2026-10-16T00:00:00Z" }),
    row({ discovered_at: "2026-10-25T04:04:04Z" }),
    row({ discovered_at: "2026-11-01T04:04:05Z" }),
    row({ discovered_at: null }),
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
  assert.match(comp, /<Panel title="Where competitors are active" info=/);
  assert.match(comp, /HEATMAP_CAPTION = "By category, in the same week as the cards below\."/);
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
  assert.match(comp, /<ItemTitle title=\{r\.title\} url=\{r\.url\} publisher=\{r\.publisher\} onOpen=\{\(\) => drawer\.open\(r\.item_id!\)\} \/>/);
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

test("the heatmap counts as the cards and says so; no Total row (D86: the card shows it); the totals line matches the cards' header", () => {
  assert.match(comp, /HEATMAP_COUNTS = "Published articles, counted as on the competitor cards: by the date they were found, in the same week\. Items awaiting review are not in this grid; each card shows them\.";/);
  assert.match(comp, /<Panel title="Where competitors are active" info=\{HEATMAP_COUNTS\}>/);
  assert.doesNotMatch(comp, /Total \(as on the card\)|data-total-row|hm\.colTotals/);
  assert.match(comp, /\{hm\.published\}<\/b> published[\s\S]*?the same as the cards below/);
});
test("1 Nov demo: every column total equals its card's number", () => {
  // GET /competitors items_7d on the 1 Nov snapshot; checked live against the heatmap: all equal, 127 in all
  const cards = { cloudsmith: 9, sonatype: 5, github: 73, gitlab: 17, snyk: 14, aws: 9 };
  assert.equal(Object.values(cards).reduce((a, b) => a + b, 0), 127);
});

test("D89: no \"published items found\" and no \"last 7 days\" label on the Competitors view", () => {
  const parts = readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8");
  assert.match(parts, /\{c\.items_7d\}<\/b>\s*<span className="text-mute">· \{c\.items_today\} in this Brief<\/span>/);
  const visible = (s) => s.replace(/\/\/.*|\/\*[\s\S]*?\*\//g, "");
  for (const s of [parts, comp, page]) assert.doesNotMatch(visible(s), /published items found|last 7 days/i);
});
