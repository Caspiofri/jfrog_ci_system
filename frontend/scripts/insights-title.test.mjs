// npm test: the insights section title follows the window the generator used (insights.window.days).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { insightsTitle } from "../src/lib/insightsTitle.ts";

test("7 days is 'Weekly insights' (1 Nov and 2 Nov served days: 7)", () => {
  assert.equal(insightsTitle({ from: "2026-10-25", to: "2026-11-01", days: 7 }), "Weekly insights");
});

test("a widened window names its length", () => {
  assert.equal(insightsTitle({ days: 14 }), "Insights · last 14 days");
  assert.equal(insightsTitle({ days: 10 }), "Insights · last 10 days");
});

test("no window served (older data, or an insights state with none): a plain title, no error", () => {
  for (const w of [undefined, null, {}, { days: 0 }, { days: "x" }]) assert.equal(insightsTitle(w), "Insights");
});

test("the Brief uses it, with the AI label next to it", () => {
  const src = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");
  assert.match(src, /\{insightsTitle\(insights\.window\)\}\s*<AiLabel \/>/);
  assert.doesNotMatch(src, /Key insights/);
});
