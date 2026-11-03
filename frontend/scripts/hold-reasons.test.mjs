// npm test: hold reasons held at every level read "Always reviewed: …" with a plain hover (src/lib/holdReasons.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { ALWAYS_REVIEWED, holdChip } from "../src/lib/holdReasons.ts";

const ALL = ["strict", "balanced", "relaxed"];
// the reasons ci/route.py holds at every level (ALL)
const EVERY_LEVEL = ["pricing", "m_and_a", "mentions_jfrog", "model_failure", "invalid_output", "changed_cell"];

test("mentions JFrog: the agreed label and hover", () => {
  const c = holdChip({ code: "mentions_jfrog", detail: "the item mentions JFrog", held_at: ALL }, "Mentions JFrog");
  assert.equal(c.label, "Always reviewed: mentions JFrog");
  assert.equal(c.levels, null);
  assert.equal(c.hint, "Items that mention JFrog always go to an analyst, whatever the autonomy setting (Strict, Balanced or Relaxed).");
});

test("every every-level reason follows the same pattern", () => {
  for (const code of EVERY_LEVEL) {
    const c = holdChip({ code, detail: "x", held_at: ALL }, code);
    assert.match(c.label, /^Always reviewed: /, code);
    assert.match(c.hint, /always go(es)? to an analyst, whatever the autonomy setting \(Strict, Balanced or Relaxed\)\.$/, code);
    assert.ok(ALWAYS_REVIEWED[code], code);
  }
});

test("a reason held at some levels keeps its label, its levels and the API's detail", () => {
  const c = holdChip({ code: "unvetted_source", detail: "publisher host x.com is not on the vetted list", held_at: ["strict"] }, "Unvetted source");
  assert.equal(c.label, "Unvetted source");
  assert.equal(c.levels, "Strict");
  assert.equal(c.hint, "publisher host x.com is not on the vetted list");
});

test("an unknown every-level reason still reads as always reviewed", () => {
  const c = holdChip({ code: "new_reason", detail: "d", held_at: ALL }, "New reason");
  assert.equal(c.label, "Always reviewed: new reason");
  assert.match(c.hint, /whatever the autonomy setting/);
});

test("the queue no longer says \"every level\"", () => {
  const src = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(src, /every level/);
  assert.match(src, /holdChip\(h, label\(HOLD_LABEL, h\.code\)\)/);
});
