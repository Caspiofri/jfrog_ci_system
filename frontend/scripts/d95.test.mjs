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

test("D113: one interim warning box replaces the caption and the hand-check line, keeping the 3 Nov date", () => {
  const m = src("components/competitors/Matrix.tsx");
  assert.match(m, /INTERIM_NOTE = "Interim view: values are AI-extracted from public pages, with no automatic verification or evaluation\. Checked manually on 3 Nov 2026 \(see README\)\.";/);
  assert.match(m, /data-interim-note>\s*<AlertTriangle [^>]*\/>\s*<span>\{INTERIM_NOTE\}<\/span>/);
  assert.doesNotMatch(m, /Checked once by hand|UnverifiedNote|data-hand-check/);
});
