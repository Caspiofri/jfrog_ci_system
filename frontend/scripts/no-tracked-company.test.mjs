// npm test: competitor "none" is shown as "No tracked company" everywhere; the value stays "none".
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { NONE_LABEL, competitorDisplayName, competitorFilterOptions } from "../src/lib/competitorLabel.ts";

const META = { competitors: [{ key: "github", name: "GitHub" }, { key: "industry", name: "Industry" }] };
const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

test("\"none\" reads \"No tracked company\"; Industry and others keep their names", () => {
  assert.equal(NONE_LABEL, "No tracked company");
  assert.equal(competitorDisplayName(META, "none"), "No tracked company");
  assert.equal(competitorDisplayName(undefined, "none"), "No tracked company");
  assert.equal(competitorDisplayName(META, "industry"), "Industry");
  assert.equal(competitorDisplayName(META, "github"), "GitHub");
  assert.equal(competitorDisplayName(META, null), "—");
});

test("filters offer it with the underlying value \"none\", after the API's competitors, once", () => {
  const o = competitorFilterOptions(META);
  assert.deepEqual(o.at(-1), { value: "none", label: "No tracked company" });
  assert.deepEqual(o.slice(0, 2), [{ value: "github", label: "GitHub" }, { value: "industry", label: "Industry" }]);
  const withNone = competitorFilterOptions({ competitors: [...META.competitors, { key: "none", name: "none" }] });
  assert.equal(withNone.filter((x) => x.value === "none").length, 1);
});

test("every screen's name and every competitor filter go through it (Brief, Review, Log, drawer)", () => {
  assert.match(read("../src/lib/meta.ts"), /return competitorDisplayName\(meta, key\)/);
  for (const p of ["../src/app/brief/page.tsx", "../src/app/review/page.tsx", "../src/app/log/page.tsx"]) {
    const src = read(p);
    assert.match(src, /ariaLabel="Competitor" allLabel="All competitors"[^\n]*\n\s*options=\{competitorFilterOptions\(meta\)\}/, p);
  }
  assert.match(read("../src/components/ItemDrawer.tsx"), /<CompetitorLabel k=\{it\.competitor\} \/>/);
});
