// npm test: D95, two text-only additions. "no price listed" reads "price not captured" on the Pricing model row
// (stored value unchanged), and the hand-check line sits right under the D88 caption on "JFrog vs competitors".
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { buildMatrix, displayValue } from "../src/lib/matrix.ts";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const GITLAB = "Free (no price listed); Premium (no price listed); Ultimate (no price listed)"; // as stored on 1 Nov

test("Pricing model only: every \"no price listed\" reads \"price not captured\"", () => {
  assert.equal(displayValue("pricing_model", GITLAB), "Free (price not captured); Premium (price not captured); Ultimate (price not captured)");
  assert.equal(displayValue("deployment", "no price listed"), "no price listed");
  assert.equal(displayValue("pricing_model", null), null);
});

test("the matrix and the profile table use it; the stored cell is not changed", () => {
  const cell = { state: "value", value: GITLAB };
  const rows = buildMatrix([{ key: "gitlab", axes: [{ axis: "pricing_model", label: "Pricing model", jfrog: { state: "not_tracked" }, competitor: cell }] }]);
  assert.match(rows[0].cells.gitlab.full, /price not captured/);
  assert.doesNotMatch(rows[0].cells.gitlab.full, /no price listed/);
  assert.equal(cell.value, GITLAB);
  const h2h = src("components/competitors/HeadToHead.tsx");
  assert.match(h2h, /<span>\{displayValue\(axis, c\.value\)\}<\/span>/);
  assert.match(h2h, /displayValue\(axis, h\.value\)/);
  assert.match(h2h, /<CellView c=\{a\.competitor\} axis=\{a\.axis\} \/>/);
});

test("the hand-check line, as written, right after the D88 caption, visible", () => {
  const m = src("components/competitors/Matrix.tsx");
  assert.match(m, /HAND_CHECK_LINE = "Checked once by hand against the live pages on 3 Nov 2026\. See the README for results\.";/);
  assert.match(m, /<UnverifiedNote \/>\s*<p [^>]*data-hand-check>\{HAND_CHECK_LINE\}<\/p>/);
});
