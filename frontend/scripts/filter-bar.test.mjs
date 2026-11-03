// npm test: the Review queue filter bar polish. Three layers: the header count; row 1, what is shown (status, search,
// sort); row 2, filter chips. Every filter, its URL param and its aria label stay as before.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");
const bar = readFileSync(new URL("../src/components/review/FilterBar.tsx", import.meta.url), "utf8");

test("header count: \"N of N held at <level>\", or \"Showing N of <whole queue> held at <level>\" when filtered", () => {
  assert.match(page, /const countLine = `\$\{filtered \? "Showing " : ""\}\$\{rows\.length\} of \$\{whole\} \$\{what\}`;/);
  assert.match(page, /filtered \? r\.backlog_total \?\? r\.total : r\.total/);
  assert.match(page, /cap=\{<span data-queue-count>\{countLine\}<\/span>\}/);
});

test("row 1: status control, search with the short placeholder, quiet sort", () => {
  assert.match(page, /<StatusControl ariaLabel="Decision"[^\n]*options=\{viewOptions\} \/>/);
  assert.match(page, /placeholder="Search id, title or publisher"/);
  assert.match(page, /<SortControl ariaLabel="Sort"/);
  assert.match(bar, /if \(options\.length <= 3\) \{[\s\S]*?aria-pressed=/); // segmented up to three, else one pill dropdown
  assert.match(bar, /Sort: <span[^>]*>\{cur\}<\/span>/);
});

test("row 2: the five filters as chips, same params; Clear all only while one is active", () => {
  for (const [name, aria, param] of [["Brief day", "Window", "brief"], ["Score", "Score", "score"], ["Category", "Category", "category"],
    ["Competitor", "Competitor", "competitor"], ["Hold reason", "Hold reason", "reason"]]) {
    assert.match(page, new RegExp(`<FilterChip name="${name}" ariaLabel="${aria}"[^\\n]*set\\(\\{ ${param}: v, offset: null \\}\\)`), name);
  }
  assert.match(page, /\{anyFilter \? \([\s\S]*?data-clear-all>Clear all<\/button>/);
  assert.match(page, /set\(\{ brief: null, score: null, category: null, competitor: null, reason: null, offset: null \}\)/);
});

test("chip looks: dashed when inactive with just the name; tinted \"Name: value\" with an x when active", () => {
  assert.match(bar, /active \? "border-jgreen\/50 bg-accent text-ink" : "border-dashed border-line bg-white/);
  assert.match(bar, /\{active \? `\$\{name\}: \$\{cur \? \(display \? display\(cur\) : cur\.label\) : value\}` : name\}/);
  assert.match(bar, /aria-label=\{`Clear \$\{name\.toLowerCase\(\)\} filter`\}/);
  assert.doesNotMatch(page, /<FilterSelect\b/);
});
