// npm test: long explanations live in hover hints (mouse and keyboard focus); what must stay visible stays visible.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const ci = read("components/ci.tsx");
const brief = read("app/brief/page.tsx");
const review = read("app/review/page.tsx");

test("the hint opens on keyboard focus too: a focusable button with a name", () => {
  const hint = ci.slice(ci.indexOf("export function InfoHint"), ci.indexOf("export function PageHead"));
  assert.match(hint, /<button type="button" aria-label=\{aria\}/);
  assert.match(hint, /focus-visible:ring/);
  assert.match(hint, /TooltipContent/);
  assert.match(ci, /export function Hint[\s\S]*?tabIndex=\{0\}/);
});

test("page descriptions moved from a subtitle line into the title's hint", () => {
  for (const f of ["app/review/page.tsx", "app/log/page.tsx", "app/health/page.tsx", "app/roadmap/page.tsx", "app/capabilities/page.tsx", "app/competitors/page.tsx"]) {
    const s = read(f);
    assert.match(s, /<PageHead[^>]*\binfo=/, `${f} uses info`);
    assert.doesNotMatch(s, /<PageHead[^>]*\bsub="/, `${f} still has a descriptive subtitle`);
  }
});

test("Brief: the window line and the published-list paragraph are hints, not paragraphs", () => {
  assert.doesNotMatch(brief, /<div className="-mt-2 text-xs text-mute">/);
  assert.doesNotMatch(brief, /<p className="m-0 -mt-1 mb-2 text-xs text-mute">/);
  assert.match(brief, /info=\{`The items found in this Brief's window/);
  assert.doesNotMatch(brief, /<WindowLine/);
  assert.match(brief, /info=\{windowText\(insights\.window\)\}/);
});

test("Review: level help is on hover of each level, not a visible line", () => {
  assert.doesNotMatch(review, /<span className="block text-\[11px\] text-mute">\{LEVEL_HELP/);
  assert.match(review, /<Hint key=\{l\.level\} text=\{LEVEL_HELP\[l\.level\]\} asChild>/);
});

test("kept visible: Experimental chip, the measured line, the AI warning, Feed date, the sort line, actions", () => {
  assert.match(brief, />Experimental<\/Tag>/);
  assert.match(brief, /<p className="[^"]*">\{INSIGHTS_CHECK\}<\/p>/);
  assert.match(brief, /AI-generated — check the cited sources/);
  assert.match(read("components/ItemDrawer.tsx") + read("components/competitors/parts.tsx"), /Feed date/);
  assert.match(review, /\{SORT_ORDER_LINE\}/);
  assert.match(brief, /Review these/);
  assert.match(brief, /Refresh insights/);
});
