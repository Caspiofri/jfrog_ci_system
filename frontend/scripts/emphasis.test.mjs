// npm test: numbers, currency amounts and "+" in bold in the capability values; display only, dates untouched.
import assert from "node:assert/strict";
import { test } from "node:test";
import { emphasize } from "../src/lib/emphasis.ts";

const show = (t) => emphasize(t).map((p) => (p.bold ? `**${p.text}**` : p.text)).join("");

test("the pieces join back to exactly the original text", () => {
  for (const t of ["Free $0; Team $4/user/month", "Supports 60+ artifact types", "MCP Registry (Mar 2026): approved", "", "no numbers here"]) {
    assert.equal(emphasize(t).map((p) => p.text).join(""), t);
  }
});

test("currency amounts, numbers and + are bold", () => {
  assert.equal(show("Cloud Pro $1,200/year; Credit $0.07/GB"), "Cloud Pro **$1,200**/year; Credit **$0.07**/GB");
  assert.equal(show("Supports 60+ artifact types"), "Supports **60+** artifact types");
  assert.equal(show("serving from 600 points"), "serving from **600** points");
  assert.equal(show("Enterprise + (no price listed)"), "Enterprise **+** (no price listed)");
});

test("dates stay plain: years, month and year, month and day, ISO dates", () => {
  for (const t of ["MCP Registry (Mar 2026)", "Traffic Controller (Sept 2026)", "as of Oct 30, 2026", "checked 2026-10-30", "since 2024"]) {
    assert.ok(emphasize(t).every((p) => !p.bold), t);
  }
  assert.equal(show("as of 2026-10-30, 14-day hold"), "as of 2026-10-30, **14**-day hold");
});
