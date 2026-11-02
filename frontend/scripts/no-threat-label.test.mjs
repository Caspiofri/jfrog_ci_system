// npm test: the competitor views say "top score", never "threat" (the field is the highest item score this week).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const visible = (s) => s.replace(/\/\/.*|\/\*[\s\S]*?\*\//g, "").replace(/\bc\.threat\b/g, "");
for (const f of ["app/competitors/page.tsx", "app/competitors/[key]/page.tsx", "components/competitors/parts.tsx", "components/competitors/Matrix.tsx"]) {
  test(`${f}: no "threat" label`, () => {
    assert.doesNotMatch(visible(readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8")), /threat/i);
  });
}
test("cards and profile say top score", () => {
  assert.match(readFileSync(new URL("../src/components/competitors/parts.tsx", import.meta.url), "utf8"), /top score <ScoreBadge score=\{c\.threat\} \/>/);
  assert.match(readFileSync(new URL("../src/app/competitors/[key]/page.tsx", import.meta.url), "utf8"), /Top score this week <ScoreBadge/);
});
