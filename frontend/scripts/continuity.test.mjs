// npm test: insight continuity badges and the "no longer appear" line (src/lib/continuity.ts, contract §14).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { CONTINUITY_TIP, continuityBadge, goneLine } from "../src/lib/continuity.ts";

const fmt = (d) => ({ "2026-10-31": "Oct 31" })[d] ?? d;

test("new", () => {
  assert.deepEqual(continuityBadge({ status: "new", since: null, new_stories: null, matched: [] }, fmt), { status: "new", text: "New" });
});

test("continuing: names the previous Brief's date, not a start date", () => {
  const b = continuityBadge({ status: "continuing", since: "2026-10-31", new_stories: 0, matched: ["ins_2026-10-31_1"] }, fmt);
  assert.deepEqual(b, { status: "continuing", text: "Also in previous Brief (Oct 31)" });
  assert.doesNotMatch(b.text, /since|started|continuing/i);
});

test("strengthened: + N new source(s), singular and plural", () => {
  assert.equal(continuityBadge({ status: "strengthened", since: "2026-10-31", new_stories: 1 }, fmt).text,
    "Also in previous Brief (Oct 31) · +1 new source");
  assert.equal(continuityBadge({ status: "strengthened", since: "2026-10-31", new_stories: 3 }, fmt).text,
    "Also in previous Brief (Oct 31) · +3 new sources");
});

test("missing field (older data): no badge, no error", () => {
  for (const c of [undefined, null, {}, "x", { status: "unknown" }]) assert.equal(continuityBadge(c, fmt), null);
});

test("a match with no previous date shows no badge rather than a wrong one", () => {
  assert.equal(continuityBadge({ status: "continuing", since: null, new_stories: 0 }, fmt), null);
});

test("strengthened with 0 or no count reads as continuing, never '+0'", () => {
  for (const n of [0, null, undefined]) {
    const b = continuityBadge({ status: "strengthened", since: "2026-10-31", new_stories: n }, fmt);
    assert.equal(b.text, "Also in previous Brief (Oct 31)");
  }
});

test("the tooltip wording", () => {
  assert.equal(CONTINUITY_TIP, "Matched to an insight of the previous Brief by shared cited stories.");
});

test("'no longer appear' line only when N > 0", () => {
  assert.equal(goneLine({ date: "2026-10-31", status: "ok", insights: 4, unmatched: 2, unmatched_ids: ["a", "b"] }),
    "2 of the previous Brief's insights no longer appear");
  assert.equal(goneLine({ date: "2026-10-31", status: "ok", insights: 4, unmatched: 1 }), "1 of the previous Brief's insights no longer appear");
  assert.equal(goneLine({ date: "2026-10-31", status: "ok", insights: 4, unmatched: 0 }), null);
  assert.equal(goneLine({ date: null, status: null, insights: 0, unmatched: 0 }), null); // first Brief
  assert.equal(goneLine(undefined), null); // older data
  assert.equal(goneLine(null), null);
});

test("the Brief puts the badge next to the pattern chip and the line under the insights title", () => {
  const src = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");
  assert.match(src, /<Tag>\{label\(PATTERN_LABEL, ins\.pattern\)\}<\/Tag>\s*<ContinuityBadge c=\{ins\.continuity\} \/>/);
  assert.match(src, /\{goneLine\(insights\.previous\) \? <p[^>]*data-gone-line>/);
  assert.match(src, /<Hint text=\{CONTINUITY_TIP\}>/);
});
