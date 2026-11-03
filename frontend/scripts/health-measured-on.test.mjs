// npm test: each Health measurement shows its own "Measured on" date; no negative age; "nothing missed" only on an
// empty list; a panel with no data says why. Mock Health blocks only (src/lib/healthMeasures.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { ageLabel, hasCoverageCounts, measuredLabel, missedState } from "../src/lib/healthMeasures.ts";
import { fmtDate, fmtDateTime } from "../src/lib/format.ts";

const parts = readFileSync(new URL("../src/components/health/parts.tsx", import.meta.url), "utf8");
// mocks: shapes as GET /health returns them (live 8011), plus BE's new coverage field measured_on
const COVERAGE = { status: "ok", measured_on: "2026-11-03", run_id: "r", list: "held-out", window: { first: "2026-10-27", last: "2026-11-02" },
  overall: { captured: 1, n: 2 }, important: { captured: 1, n: 1, min_score: 4 }, by_source_kind: {}, missed: [] };
const CHANGE_IN_DEMO = { status: "ok", run_id: "c", started_at: "2026-11-03T04:05:48Z", live: true, age_hours: -48 };

test("\"Measured on <date>\" from the given date; a missing date is said, not left blank", () => {
  assert.equal(measuredLabel("2026-11-03", (d) => fmtDate(d, true)), "Measured on Nov 3, 2026");
  assert.equal(measuredLabel(CHANGE_IN_DEMO.started_at, fmtDateTime), `Measured on ${fmtDateTime(CHANGE_IN_DEMO.started_at)}`);
  for (const d of [undefined, null, ""]) assert.equal(measuredLabel(d, fmtDate), "Measurement date not recorded.");
});

test("an age is shown only when it is zero or more (demo clock before the run gives a negative age)", () => {
  assert.equal(ageLabel(CHANGE_IN_DEMO.age_hours), null);
  assert.equal(ageLabel(-0.1), null);
  assert.equal(ageLabel(undefined), null);
  assert.equal(ageLabel(null), null);
  assert.equal(ageLabel(0), "0 h ago");
  assert.equal(ageLabel(5.5), "5.5 h ago");
});

test("\"nothing missed\" only for an empty list; an absent list claims nothing", () => {
  assert.equal(missedState(COVERAGE.missed), "none");
  assert.equal(missedState([{ id: "x" }]), "list");
  assert.equal(missedState(undefined), "unknown");
  assert.equal(missedState(null), "unknown");
});

test("a coverage block with no counts has no data", () => {
  assert.equal(hasCoverageCounts(COVERAGE), true);
  assert.equal(hasCoverageCounts({ status: "ok" }), false);
  assert.equal(hasCoverageCounts({ status: "ok", by_source_kind: {} }), false);
  assert.equal(hasCoverageCounts({ status: "ok", by_source_kind: { feed: { captured: 1, n: 1 } } }), true);
});

test("coverage: Measured on from measured_on, nothing-missed only when empty, reason when no counts", () => {
  assert.match(parts, /measuredLabel\(cv\.measured_on, \(d\) => fmtDate\(d, true\)\)/);
  assert.match(parts, /if \(cv\.status !== "ok" \|\| !hasCoverageCounts\(cv\)\) return <Empty>\{missing\}<\/Empty>;/);
  assert.match(parts, /missedState\(cv\.missed\) === "none" \? <div className="text-xs text-mute">Nothing on the list was missed\.<\/div> : null/);
  assert.match(readFileSync(new URL("../src/lib/types.ts", import.meta.url), "utf8"), /measured_on\?: string \| null;/);
});

test("change detection: Measured on its start time, age only through ageLabel", () => {
  assert.match(parts, /measuredLabel\(c\.started_at, fmtDateTime\)/);
  assert.match(parts, /ageLabel\(c\.age_hours\)/);
  assert.doesNotMatch(parts, /`\$\{c\.age_hours\} h ago`/);
});

test("test split and accuracy label their date \"Measured on\"", () => {
  assert.match(parts, /fact\("Measured on", t\.created_at \? fmtDateTime\(t\.created_at\) : "Not recorded"\)/);
  assert.doesNotMatch(parts, /fact\("Run on"/);
  assert.match(parts, /\{measuredLabel\(ev\.created_at, fmtDateTime\)\} · report \{ev\.report\}/);
});

test("article text says so when the picked scope has no data; run history says so when it can't load", () => {
  assert.match(parts, /\) : <span className="text-mute">Not measured for this scope\.<\/span>\}/);
  const page = readFileSync(new URL("../src/app/health/page.tsx", import.meta.url), "utf8");
  assert.match(page, /runs\.error \? <Empty>The run history could not be loaded\.<\/Empty>/);
});
