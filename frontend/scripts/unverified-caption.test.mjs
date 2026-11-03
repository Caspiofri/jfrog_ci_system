// npm test: D88, the unverified-values caption, visible (not a hover) on the three places that show head-to-head or
// change-detection values; the "not a verdict" caption stays on "JFrog vs competitors".
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { UNVERIFIED_VALUES } from "../src/lib/format.ts";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("the caption is exactly as given", () => {
  assert.equal(UNVERIFIED_VALUES, "Values are extracted by an AI model from the linked public pages. The system has no verification step for them, and our evaluation does not cover them. Check the source before relying on a value.");
});

test("rendered as visible text, not a title or hover", () => {
  assert.match(src("components/ci.tsx"), /export function UnverifiedNote[\s\S]*?<span>\{UNVERIFIED_VALUES\}<\/span>/);
});

test("on JFrog vs competitors, the profile's head-to-head table and the Health change-detection panel", () => {
  assert.match(src("components/competitors/Matrix.tsx"), /<Panel title="JFrog vs competitors"[\s\S]*?<UnverifiedNote/);
  assert.match(src("components/competitors/HeadToHead.tsx"), /<UnverifiedNote[\s\S]*?<table/);
  assert.match(src("app/health/page.tsx"), /<Panel title="Did the tracked pages change\?"[^>]*>\s*<UnverifiedNote/);
});

test("the \"not a verdict\" caption stays", () => {
  assert.match(src("components/competitors/Matrix.tsx"), /CAPTION = "What was found on public pages, not a verdict\.";[\s\S]*?\{CAPTION\}/);
});
