// npm test: a Health panel with no data shows a short reason, never a blank or a row of dashes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { NOT_IN_SNAPSHOT, NOT_MEASURED, noDataReason } from "../src/lib/healthReasons.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

test("demo mode says the snapshot left it out; live says not measured", () => {
  assert.equal(noDataReason("demo"), "Not included in this demo snapshot.");
  assert.equal(noDataReason("live"), "Not measured yet.");
  assert.equal(noDataReason(undefined), NOT_MEASURED);
  assert.equal(NOT_IN_SNAPSHOT, "Not included in this demo snapshot.");
});

test("test split, accuracy, coverage and change detection show the reason when they have no data", () => {
  const parts = read("../src/components/health/parts.tsx");
  assert.match(parts, /export function TestEvalBlock\(\{ t, missing \}[\s\S]*?if \(!ran\) return <Empty>\{missing\}<\/Empty>;/);
  assert.match(parts, /export function EvalCards\(\{ ev, missing \}[\s\S]*?if \(ev\.status !== "ok"\) return <Empty>\{missing\}<\/Empty>;/);
  assert.match(parts, /export function Coverage\(\{ cv, missing \}[\s\S]*?if \(cv\.status !== "ok" \|\| !hasCoverageCounts\(cv\)\) return <Empty>\{missing\}<\/Empty>;/);
  assert.match(parts, /export function ChangeDetection\(\{ c, missing \}[\s\S]*?if \(c\.status === "none"\) return <Empty>\{missing\}<\/Empty>;/);
});

test("the Health page passes the mode's reason to every one of them, and to absent fields", () => {
  const page = read("../src/app/health/page.tsx");
  assert.match(page, /const missing = noDataReason\(meta\?\.meta\?\.mode\);/);
  for (const re of [/<TestEvalBlock t=\{h\.test_eval\} missing=\{missing\} \/>/,
    /\{h\.eval \? <EvalCards ev=\{h\.eval\} missing=\{missing\} \/> : <Empty>\{missing\}<\/Empty>\}/,
    /\{h\.coverage \? <Coverage cv=\{h\.coverage\} missing=\{missing\} \/> : <Empty>\{missing\}<\/Empty>\}/,
    /\{h\.change_detection \? <ChangeDetection c=\{h\.change_detection\} missing=\{missing\} \/> : <Empty>\{missing\}<\/Empty>\}/,
    /\{h\.extraction \? <Extraction e=\{h\.extraction\} \/> : <Empty>\{missing\}<\/Empty>\}/]) assert.match(page, re);
});
