// npm test: the Brief's competitor and category filters sit above the items list, below the insights.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("filters are in the items panel, not the page header", () => {
  const p = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");
  const screen = p.slice(p.indexOf("function BriefScreen"), p.indexOf("function SummaryBlock"));
  const head = screen.slice(screen.indexOf("<PageHead"), screen.indexOf("<ImportanceLegend"));
  assert.doesNotMatch(head, /FilterSelect|tools=/);
  const ins = screen.indexOf("<InsightsPanel"), filters = screen.indexOf("data-brief-filters"), list = screen.indexOf("b.items.items.map");
  assert.ok(ins > 0 && ins < filters && filters < list);
  assert.match(screen.slice(filters, list), /ariaLabel="Competitor"[\s\S]*ariaLabel="Category"/);
});
