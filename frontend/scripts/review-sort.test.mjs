// npm test: the Review queue's sort selector (src/lib/reviewQueue.ts), over the whole queue held in the browser.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { SORT_LINES, SORT_OPTIONS, sortQueue } from "../src/lib/reviewQueue.ts";

const item = (id, published_at) => ({ kind: "item", item: { item_id: id, published_at } });
const change = (id) => ({ kind: "change", change_id: id });
// the API's (importance) order
const API = [change("c1"), item("a", "2026-10-30T10:00:00Z"), item("b", "2026-11-01T08:00:00Z"), item("n", null),
  item("c", "2026-10-28T09:00:00Z"), item("d", "2026-11-01T08:00:00Z")];
const ids = (rows) => rows.map((r) => (r.kind === "change" ? r.change_id : r.item.item_id));

test("Importance is the default and keeps the API's order", () => {
  assert.deepEqual(ids(sortQueue(API, "")), ids(API));
  assert.equal(SORT_OPTIONS[0].value, "");
  assert.equal(SORT_OPTIONS[0].label, "Importance");
  assert.deepEqual(SORT_OPTIONS.map((o) => o.label), ["Importance", "Newest first", "Oldest first"]);
});

test("Newest first by feed date; changed cells stay on top; no feed date last; ties keep the API order", () => {
  assert.deepEqual(ids(sortQueue(API, "newest")), ["c1", "b", "d", "a", "c", "n"]);
});

test("Oldest first by feed date", () => {
  assert.deepEqual(ids(sortQueue(API, "oldest")), ["c1", "c", "a", "b", "d", "n"]);
});

test("sorting never changes the input array", () => {
  const copy = [...API];
  sortQueue(API, "newest");
  assert.deepEqual(API, copy);
});

test("the line under the filters states the order shown", () => {
  assert.match(SORT_LINES[""], /^Sorted as the API returns them/);
  assert.match(SORT_LINES.newest, /newest article date first/i);
  assert.match(SORT_LINES.oldest, /oldest article date first/i);
  for (const k of ["newest", "oldest"]) assert.match(SORT_LINES[k], /changed head-to-head cells first/i);
});

test("the page sorts after filtering, over the whole queue, and shows the matching line", () => {
  const src = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");
  assert.match(src, /sortQueue\(filterQueue\(base, local\), sort\)/); // base: the queue, or the decided view (D91)
  assert.match(src, /SORT_LINES\[sort\]/);
  assert.match(src, /ariaLabel="Sort"/);
  assert.match(src, /getWholeQueue/);
});
