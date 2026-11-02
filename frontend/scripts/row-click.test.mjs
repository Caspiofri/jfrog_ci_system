// npm test: in the Review queue (and every item list using ItemRow), a click on the row opens the side drawer.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const row = readFileSync(new URL("../src/components/ItemRow.tsx", import.meta.url), "utf8");
const review = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");

test("the whole row opens the item's drawer; the title stays a button for the keyboard", () => {
  assert.match(row, /onClick=\{\(e\) => openFromRow\(e, \(\) => drawer\.open\(item\.item_id\)\)\}/);
  assert.match(row, /<ItemTitle title=\{item\.title\} url=\{item\.url\} onOpen=\{\(\) => drawer\.open\(item\.item_id\)\}/);
  assert.match(review, /<ItemRow\b/);
});

test("its own controls, portals (Edit dialog, Dismiss menu) and text selection don't open it", () => {
  const fn = row.slice(row.indexOf("function openFromRow"));
  assert.match(fn, /if \(!e\.currentTarget\.contains\(t\)\) return;/);
  assert.match(fn, /if \(t\.closest\(INTERACTIVE\)\) return;/);
  assert.match(fn, /getSelection\(\)\?\.toString\(\)\) return;/);
  for (const sel of ["button", "a", "input", "textarea", "[role='menuitem']", "[role='dialog']"]) assert.ok(row.includes(sel), sel);
});
