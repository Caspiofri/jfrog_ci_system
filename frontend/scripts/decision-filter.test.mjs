// npm test: D91, the review queue's decision filter. Needs decision (the default) is GET /review; Approved, Dismissed
// and All add the decided items from GET /log, in the same scope. Nothing here changes a status or an action.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { DECIDED_STATUSES, decidedIds, decisionOptions, inQueueScope } from "../src/lib/reviewQueue.ts";

const page = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");

test("decided items once each, in the Log's order; undecided rows ignored", () => {
  assert.deepEqual(decidedIds([
    { item_id: "a", status: "approved" }, { item_id: "a", status: "approved" }, { item_id: "b", status: "awaiting_review" },
    { item_id: "c", status: "dismissed" }, { item_id: null, status: "dismissed" }, { item_id: "d", status: "flagged" },
  ]), ["a", "c", "d"]);
  assert.deepEqual(DECIDED_STATUSES, ["approved", "dismissed", "flagged"]);
});

test("same scope as GET /review: Brief window (prev_anchor, anchor] and the reason at the level", () => {
  const w = { prev_anchor: "2026-10-31T13:45:36Z", anchor: "2026-11-01T04:00:01Z" };
  const it = (d, hr = []) => ({ discovered_at: d, hold_reasons: hr });
  assert.equal(inQueueScope(it("2026-11-01T04:00:01Z"), { window: w, level: "strict" }), true);
  assert.equal(inQueueScope(it("2026-10-31T13:45:36Z"), { window: w, level: "strict" }), false);
  assert.equal(inQueueScope(it(null), { window: w, level: "strict" }), false);
  assert.equal(inQueueScope(it(null), { window: null, level: "strict" }), true);
  const held = [{ code: "pricing", held_at: ["strict", "balanced", "relaxed"] }, { code: "unvetted_source", held_at: ["strict"] }];
  assert.equal(inQueueScope(it(null, held), { reason: "unvetted_source", level: "strict" }), true);
  assert.equal(inQueueScope(it(null, held), { reason: "unvetted_source", level: "balanced" }), false);
});

test("options with counts; Needs decision first (the default); Dismissed only when the data has it", () => {
  const n = { needs: 110, approved: 1, dismissed: 2, all: 113 };
  assert.deepEqual(decisionOptions(n, true).map((o) => [o.value, o.label]),
    [["", "Needs decision (110)"], ["approved", "Approved (1)"], ["dismissed", "Dismissed (2)"], ["all", "All (113)"]]);
  assert.deepEqual(decisionOptions(n, false).map((o) => o.value), ["", "approved", "all"]);
});

test("the page: default is GET /review; decided rows from GET /log show their status and no actions", () => {
  assert.match(page, /const view: DecisionView = viewParam === "approved" \|\| viewParam === "dismissed" \|\| viewParam === "all" \? viewParam : "";/);
  assert.match(page, /view === "" \? r\.items : view === "all" \? \[\.\.\.r\.items, \.\.\.done\] : byStatus\(view\)/);
  assert.match(page, /const rows = sortQueue\(filterQueue\(base, local\), sort\);/);
  assert.match(page, /path\("\/log", \{ status: DECIDED_STATUSES, competitor, limit: 200, offset: 0 \}\)/);
  const decided = page.slice(page.indexOf("function DecidedItem"), page.indexOf("function QueueItem"));
  assert.doesNotMatch(decided, /ItemActions|send\(|Approve|Reopen/);
});
