// npm test: a click on an item row (Review, competitor profiles) or a Brief card opens the side drawer.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const row = read("components/ItemRow.tsx");
const card = read("components/brief/BriefCard.tsx");
const ci = read("components/ci.tsx");

test("Review rows and Brief cards open the item's drawer on click; the title stays a button for the keyboard", () => {
  for (const [name, src, v] of [["ItemRow", row, "item"], ["BriefCard", card, "item"]]) {
    assert.match(src, new RegExp(`onClick=\\{\\(e\\) => openFromRow\\(e, \\(\\) => drawer\\.open\\(${v}\\.item_id\\)\\)\\}`), name);
    assert.match(src, /<ItemTitle title=\{item\.title\} url=\{item\.url\} onOpen=\{\(\) => drawer\.open\(item\.item_id\)\}/, name);
  }
  assert.match(read("app/review/page.tsx"), /<ItemRow\b/);
  assert.match(read("app/brief/page.tsx"), /<BriefCard\b/);
});

test("one shared rule: own controls, portals (dialogs, menus) and text selection don't open it", () => {
  const fn = ci.slice(ci.indexOf("export function openFromRow"));
  assert.match(fn, /if \(!e\.currentTarget\.contains\(t\)\) return;/);
  assert.match(fn, /if \(t\.closest\(INTERACTIVE\)\) return;/);
  assert.match(fn, /getSelection\(\)\?\.toString\(\)\) return;/);
  for (const sel of ["button", "a", "input", "textarea", "[role='menuitem']", "[role='dialog']"]) assert.ok(ci.includes(sel), sel);
  assert.doesNotMatch(row + card, /function openFromRow/);
});
