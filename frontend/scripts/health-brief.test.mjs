// npm test: Health's "Brief's counts" panel follows the run picked in the Run filter (src/lib/healthBrief.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { briefForRun } from "../src/lib/healthBrief.ts";

const rows = [
  { date: "2026-11-01", anchor_run_id: "20261101T0400Z-e9cae4" },
  { date: "2026-10-31", anchor_run_id: "20261031T1345Z-802913" },
  { date: "2026-10-30", anchor_run_id: "20261030T1312Z-389e71" },
];

test("no run picked: the latest Brief", () => {
  assert.deepEqual(briefForRun(rows, "", "2026-11-01"), { date: "2026-11-01", picked: false });
  assert.deepEqual(briefForRun([], "", undefined), { date: undefined, picked: false });
});

test("a run picked: the Brief anchored on that run, not the latest", () => {
  assert.deepEqual(briefForRun(rows, "20261031T1345Z-802913", "2026-11-01"), { date: "2026-10-31", picked: true });
  assert.deepEqual(briefForRun(rows, "20261030T1312Z-389e71", "2026-11-01"), { date: "2026-10-30", picked: true });
});

test("a run with no Brief of its own: no date, so the panel says so instead of showing another day's counts", () => {
  assert.deepEqual(briefForRun(rows, "20261102T0400Z-xxxxxx", "2026-11-01"), { date: null, picked: true });
});

test("the Health page passes the picked run to the Brief counts panel", () => {
  const page = readFileSync(new URL("../src/app/health/page.tsx", import.meta.url), "utf8");
  assert.match(page, /<BriefCounts runId=\{runId\} \/>/);
  assert.match(page, /briefForRun\(briefs\.data\?\.items \?\? \[\], runId, meta\?\.latest_brief_date\)/);
});
