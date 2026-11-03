// npm test: D91, the review queue's decision filter. Needs decision (the default) is GET /review; Approved, Dismissed
// and All add the decided items from GET /log, in the same scope. Nothing here changes a status or an action.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { DECIDED_STATUSES, LOG_STATUSES, decidedIds, decisionOptions, flaggedFirst, inQueueScope, isActiveFlag } from "../src/lib/reviewQueue.ts";

const page = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");

test("decided items and flagged cleared items once each, in the Log's order; other rows ignored (D107: flag is a boolean)", () => {
  assert.deepEqual(decidedIds([
    { item_id: "a", status: "approved" }, { item_id: "a", status: "approved" }, { item_id: "b", status: "awaiting_review" },
    { item_id: "c", status: "dismissed" }, { item_id: null, status: "dismissed" }, { item_id: "d", status: "auto_published", flagged: true },
    { item_id: "e", status: "auto_published", flagged: false },
  ]), ["a", "c", "d"]);
  assert.deepEqual(DECIDED_STATUSES, ["approved", "dismissed"]);
  assert.deepEqual(LOG_STATUSES, ["approved", "dismissed", "auto_published"]);
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

test("options with counts; Needs decision first (the default); Flagged always; Dismissed only when the data has it", () => {
  const n = { needs: 110, approved: 1, flagged: 2, dismissed: 2, all: 115 };
  assert.deepEqual(decisionOptions(n, true).map((o) => [o.value, o.label]),
    [["", "Needs decision (110)"], ["approved", "Approved (1)"], ["flagged", "Flagged (2)"], ["dismissed", "Dismissed (2)"], ["all", "All (115)"]]);
  assert.deepEqual(decisionOptions(n, false).map((o) => o.value), ["", "approved", "flagged", "all"]);
});

test("D107: flagged items lead Needs decision and All (stable); the Flagged view is every flagged item, held ones included", () => {
  const row = (id, status, flagged = false) => ({ kind: "item", item: { item_id: id, status, flagged } });
  const out = flaggedFirst([row("a", "awaiting_review"), row("b", "awaiting_review", true), { kind: "change", change_id: 1 }, row("c", "approved"), row("d", "auto_published", true)]);
  assert.deepEqual(out.map((r) => r.item?.item_id ?? "change"), ["b", "d", "a", "change", "c"]);
  assert.match(page, /const rows = view === "" \|\| view === "all" \? flaggedFirst\(sorted\) : sorted;/);
  assert.match(page, /const flaggedRows = \[\.\.\.r\.items\.filter\(isFlagged\), \.\.\.done\.filter\(isFlagged\)\];/);
  assert.match(page, /view === "flagged" \? flaggedRows : byStatus\(view\)/);
  assert.doesNotMatch(page, /status === "flagged"|byStatus\("flagged"\)/);
  assert.match(page, /data-flagged-count=\{counts\.flagged\}[\s\S]*?\{counts\.flagged\} flagged/);
  assert.match(page, /viewParam === "flagged"/);
});

test("the page: default is GET /review; decided rows from GET /log show their status and no actions", () => {
  assert.match(page, /const view: DecisionView = viewParam === "approved" \|\| viewParam === "flagged" \|\| viewParam === "dismissed" \|\| viewParam === "all" \? viewParam : "";/);
  assert.match(page, /view === "" \? r\.items : view === "all" \? \[\.\.\.r\.items, \.\.\.done\] : view === "flagged" \? flaggedRows : byStatus\(view\)/);
  assert.match(page, /const sorted = sortQueue\(filterQueue\(base, local\), sort\);/);
  assert.match(page, /path\("\/log", \{ status: LOG_STATUSES, competitor, limit: 200, offset: 0 \}\)/);
  const decided = page.slice(page.indexOf("function DecidedItem"), page.indexOf("function QueueItem"));
  assert.doesNotMatch(decided, /ItemActions|send\(|Approve|Reopen/);
});

test("a dismissed item that is still flagged: not counted, not in the Flagged view, not put first", () => {
  const row = (id, status, flagged) => ({ kind: "item", item: { item_id: id, status, flagged } });
  assert.equal(isActiveFlag(row("x", "dismissed", true)), false);
  assert.equal(isActiveFlag(row("y", "awaiting_review", true)), true);
  assert.equal(isActiveFlag(row("z", "approved", true)), true);
  assert.equal(isActiveFlag({ kind: "change", change_id: 1 }), false);
  const out = flaggedFirst([row("a", "awaiting_review", false), row("d", "dismissed", true), row("f", "auto_published", true)]);
  assert.deepEqual(out.map((r) => r.item.item_id), ["f", "a", "d"]);
  assert.match(page, /const isFlagged = \(x: ReviewItemRow \| ReviewChangeRow\) => isActiveFlag\(x\);/);
});
