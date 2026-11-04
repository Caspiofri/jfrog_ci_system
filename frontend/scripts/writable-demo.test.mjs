// npm test: D111 writable demo, display only.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { ACTION_OFF, INSIGHTS_FROZEN, SANDBOX_NOTE, demoState, errorText } from "../src/lib/demo.ts";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("demo_writable from /meta, top level or in meta.meta; anything else is read-only; live ignores it", () => {
  assert.equal(demoState({ meta: { mode: "live" }, demo_writable: true }), "live");
  assert.equal(demoState(undefined), "live");
  assert.equal(demoState({ meta: { mode: "demo" }, demo_writable: true }), "demo_writable");
  assert.equal(demoState({ meta: { mode: "demo", demo_writable: true } }), "demo_writable");
  assert.equal(demoState({ meta: { mode: "demo" }, demo_writable: false }), "demo_read_only");
  assert.equal(demoState({ meta: { mode: "demo" } }), "demo_read_only");
});

test("the exact sentences", () => {
  assert.equal(SANDBOX_NOTE, "Changes stay in this sandbox and reset on restart.");
  assert.equal(INSIGHTS_FROZEN,
    "Insights are frozen in this demo: generating new ones needs a live LLM connection and API key. They do not reflect changes made here.");
});

test("writable demo adds the sandbox sentence to the existing snapshot line only", () => {
  const shell = src("components/shell/Shell.tsx");
  assert.match(shell, /The live system keeps running daily at 06:00\.\s*\{demoState\(data\) === "demo_writable" \? <> \{SANDBOX_NOTE\}<\/> : null\}/);
});

test("refused writes: read-only keeps today's message; frozen insights and other coded 403s read as plain text", () => {
  const ro = { status: 403, code: "demo_read_only", message: "Demo snapshot 2026-11-03: read-only, writes are disabled" };
  assert.deepEqual(errorText(ro), { text: ro.message, showCode: true });
  assert.deepEqual(errorText({ status: 403, code: "insights_frozen_demo", message: "x" }), { text: INSIGHTS_FROZEN, showCode: false });
  assert.deepEqual(errorText({ status: 403, code: "demo_action_disabled", message: "raw" }), { text: ACTION_OFF, showCode: false });
  assert.deepEqual(errorText({ status: 409, code: "version_conflict", message: "m" }), { text: "m", showCode: true });
  const ci = src("components/ci.tsx");
  assert.match(ci, /\{text\}\s*\{code && showCode \?/);
  assert.doesNotMatch(ci, /\{error\.message\}/);
});

test("actions are not disabled by demo mode in the UI; the API decides", () => {
  assert.doesNotMatch(src("components/review/actions.tsx"), /mode === "demo"|demoState/);
  assert.doesNotMatch(src("app/review/page.tsx"), /mode === "demo"|demoState/);
});
