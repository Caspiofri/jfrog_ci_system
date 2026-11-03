// npm test: Review queue search, window selector and local filters (src/lib/reviewQueue.ts).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  FETCH_LIMIT, SCORE_OPTIONS, SORT_ORDER_LINE, filterQueue, hasLocalFilters, matchesSearch, queueQuery, remainingOffsets, windowOptions,
} from "../src/lib/reviewQueue.ts";

const item = (o) => ({
  kind: "item", held_since: "2026-11-01T04:10:00Z", trust_source: null,
  item: { item_id: "0000000000000000", title: "", publisher: "", publisher_host: "", category: "Security", score: 3, ...o },
});
const change = { kind: "change", change_id: "chg-snyk-1", run_id: "r", competitor: "snyk", axis: "pricing_model", axis_label: "Pricing model", old_value: "a", new_value: "b" };

const ROWS = [
  change,
  item({ item_id: "3f7d08fbe030f71d", title: "GitHub ships package firewall", publisher: "InfoWorld", publisher_host: "infoworld.com", score: 4, category: "Security" }),
  item({ item_id: "4cad095f0452861d", title: "Sonatype raises prices", publisher: "The Register", publisher_host: "theregister.com", score: 5, category: "Pricing & Packaging" }),
  item({ item_id: "a1b2c3d4e5f60718", title: "Docker Hub adds AI agents", publisher: "DevOps.com", publisher_host: "devops.com", score: 2, category: "AI & Agents" }),
  item({ item_id: "ffff000011112222", title: "Model failed on this one", publisher: "gbhackers", publisher_host: "gbhackers.com", score: null, category: null }),
  item({ item_id: "eeee000011112222", title: "Minor note", publisher: "Blog", publisher_host: "blog.example", score: 1, category: "Product & Features" }),
];
const ids = (rows) => rows.map((r) => (r.kind === "item" ? r.item.item_id : r.change_id));
const none = { q: "", score: "", category: "" };

test("search by full item id and by id prefix, case-insensitive", () => {
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, q: "3f7d08fbe030f71d" })), ["3f7d08fbe030f71d"]);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, q: "3F7D08" })), ["3f7d08fbe030f71d"]);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, q: "  3f7d  " })), ["3f7d08fbe030f71d"]);
});

test("id matches on the prefix only, not inside the id", () => {
  assert.equal(matchesSearch(ROWS[1], "030f71d"), false);
});

test("search by title text, case-insensitive", () => {
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, q: "package FIREWALL" })), ["3f7d08fbe030f71d"]);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, q: "agents" })), ["a1b2c3d4e5f60718"]);
});

test("search by publisher name or host", () => {
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, q: "the register" })), ["4cad095f0452861d"]);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, q: "devops.com" })), ["a1b2c3d4e5f60718"]);
});

test("search finds a changed cell by competitor or axis", () => {
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, q: "pricing model" })), ["chg-snyk-1"]);
});

test("empty search keeps every row in the API's order", () => {
  assert.deepEqual(ids(filterQueue(ROWS, none)), ids(ROWS));
  assert.equal(hasLocalFilters(none), false);
  assert.equal(hasLocalFilters({ ...none, q: "   " }), false);
  assert.equal(hasLocalFilters({ ...none, score: "3" }), true);
});

test("score filter: 4+, exact 3 / 2 / 1, and not scored; changed cells have no score", () => {
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, score: "4+" })), ["3f7d08fbe030f71d", "4cad095f0452861d"]);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, score: "3" })), []);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, score: "2" })), ["a1b2c3d4e5f60718"]);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, score: "1" })), ["eeee000011112222"]);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, score: "none" })), ["ffff000011112222"]);
  assert.deepEqual(SCORE_OPTIONS.map((o) => o.value), ["4+", "3", "2", "1", "none"]);
});

test("category filter matches the item's category exactly", () => {
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, category: "Security" })), ["3f7d08fbe030f71d"]);
  assert.deepEqual(ids(filterQueue(ROWS, { ...none, category: "AI & Agents" })), ["a1b2c3d4e5f60718"]);
});

test("filters combine with search", () => {
  assert.deepEqual(ids(filterQueue(ROWS, { q: "infoworld", score: "4+", category: "Security" })), ["3f7d08fbe030f71d"]);
  assert.deepEqual(ids(filterQueue(ROWS, { q: "infoworld", score: "2", category: "" })), []);
});

test("empty result: no match returns an empty list, not an error", () => {
  assert.deepEqual(filterQueue(ROWS, { ...none, q: "no such thing" }), []);
  assert.deepEqual(filterQueue([], { ...none, q: "3f7d" }), []);
});

test("window selector: All held items sends no brief; a Brief day sends brief=<date>", () => {
  const all = queueQuery({ level: "", reason: "", competitor: "", brief: "" });
  assert.equal(all.brief, undefined);
  assert.equal(all.limit, FETCH_LIMIT);
  assert.equal(all.offset, 0);
  const day = queueQuery({ brief: "2026-11-01", competitor: "github", reason: "unvetted_source", level: "strict" });
  assert.deepEqual(day, { level: "strict", reason: "unvetted_source", competitor: "github", brief: "2026-11-01", limit: FETCH_LIMIT, offset: 0 });
});

test("window options: one per Brief day, newest first, no duplicates", () => {
  const opts = windowOptions(["2026-10-31", "2026-11-02", "2026-11-01", "2026-11-01"], (d) => `D${d}`);
  assert.deepEqual(opts.map((o) => o.value), ["2026-11-02", "2026-11-01", "2026-10-31"]);
  assert.equal(opts[1].label, "Held from the Brief of D2026-11-01");
});

test("the whole queue is fetched: offsets after the first page", () => {
  assert.deepEqual(remainingOffsets(115, 115), []);
  assert.deepEqual(remainingOffsets(0, 0), []);
  assert.deepEqual(remainingOffsets(450, 200), [200, 400]);
});

test("the sort line states the API's order", () => {
  assert.match(SORT_ORDER_LINE, /changed head-to-head cells first.*held at every level.*score from high to low.*oldest collected first/);
  assert.doesNotMatch(SORT_ORDER_LINE, /\bD\d+\b/);
});
