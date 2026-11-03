// npm test: D89, the competitor beside "Competitor momentum", only when every cited item names one tracked competitor.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { soleCompetitor } from "../src/lib/competitorLabel.ts";

const meta = { competitors: [{ key: "github", is_industry: false }, { key: "gitlab", is_industry: false }, { key: "industry", is_industry: true }] };

test("all cited items name one tracked competitor: that competitor", () => {
  assert.equal(soleCompetitor(meta, ["github", "github", "github"]), "github");
});
test("otherwise nothing: mixed, a missing value, Industry, No tracked company, unknown key, no items, no meta", () => {
  assert.equal(soleCompetitor(meta, ["github", "gitlab"]), null);
  assert.equal(soleCompetitor(meta, ["github", null]), null);
  assert.equal(soleCompetitor(meta, ["industry", "industry"]), null);
  assert.equal(soleCompetitor(meta, ["none"]), null);
  assert.equal(soleCompetitor(meta, ["acme"]), null);
  assert.equal(soleCompetitor(meta, []), null);
  assert.equal(soleCompetitor(undefined, ["github"]), null);
});
test("shown only on Competitor momentum, with the existing avatar, from the cited items", () => {
  const src = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");
  assert.match(src, /ins\.pattern === "competitor_momentum" \? <MomentumCompetitor ins=\{ins\} \/> : null/);
  assert.match(src, /function MomentumCompetitor[\s\S]*?new Set\(ins\.item_ids\)[\s\S]*?soleCompetitor\(meta, q\.data\.map\(\(d\) => d\.item\?\.competitor\)\)[\s\S]*?<CompetitorAvatar k=\{k\}/);
});
