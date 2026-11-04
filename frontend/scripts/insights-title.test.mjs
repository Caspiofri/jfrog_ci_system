// npm test: the insights section title follows the window the generator used (insights.window.days).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { INSIGHTS_TITLE_HINT, insightsTitle } from "../src/lib/insightsTitle.ts";

test("D113: 'Cumulative insights' for a 7-day and a widened window; never 'Weekly'", () => {
  assert.equal(insightsTitle({ from: "2026-10-25", to: "2026-11-01", days: 7 }), "Cumulative insights");
  assert.equal(insightsTitle({ days: 14 }), "Cumulative insights");
  assert.equal(INSIGHTS_TITLE_HINT, "Patterns across the last 7 to 14 days, not only this Brief.");
});

test("no window served (older data, or an insights state with none): a plain title, no error", () => {
  for (const w of [undefined, null, {}, { days: 0 }, { days: "x" }]) assert.equal(insightsTitle(w), "Insights");
});

test("the Brief uses it, with the AI label next to it", () => {
  const src = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");
  assert.match(src, /<Hint text=\{INSIGHTS_TITLE_HINT\}>\{insightsTitle\(insights\.window\)\}<\/Hint>\s*<AiLabel \/>/);
  assert.doesNotMatch(src, /Weekly insights|Today in numbers/);
  assert.doesNotMatch(src, /Key insights/);
});
