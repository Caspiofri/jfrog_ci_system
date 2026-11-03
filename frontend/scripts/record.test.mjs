// npm test: one record by id (src/lib/record.ts, useRecord in lib/api.ts): never the previous record.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { isStale, pickRecord } from "../src/lib/record.ts";

const idOf = (d) => d.item?.item_id;
const A = { item: { item_id: "aaaa000000000001", title: "Item A" } };
const B = { item: { item_id: "bbbb000000000002", title: "Item B" } };

test("a 404 after a successful load shows no record (the error state), never the previous item", () => {
  assert.equal(pickRecord("aaaa000000000001", A, idOf), A); // A loads
  // B is requested and its load fails: the fetch layer may still hold A's response
  assert.equal(pickRecord("bbbb000000000002", A, idOf), undefined);
  assert.equal(isStale("bbbb000000000002", A, idOf), true); // actions stay disabled meanwhile
  assert.equal(pickRecord("bbbb000000000002", undefined, idOf), undefined);
});

test("fast switching A → B → A: a late response for the other item is never shown", () => {
  assert.equal(pickRecord("bbbb000000000002", A, idOf), undefined); // B requested, A's slow response arrives
  assert.equal(pickRecord("bbbb000000000002", B, idOf), B); // B's own response
  assert.equal(pickRecord("aaaa000000000001", B, idOf), undefined); // back to A, B's response still on hand
  assert.equal(pickRecord("aaaa000000000001", A, idOf), A);
  assert.equal(isStale("aaaa000000000001", A, idOf), false);
});

test("nothing requested or nothing loaded: no record, not stale", () => {
  assert.equal(pickRecord(null, A, idOf), undefined);
  assert.equal(pickRecord("x", null, idOf), undefined);
  assert.equal(isStale("x", undefined, idOf), false);
});

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("useRecord turns keepPreviousData off and returns only the matching record", () => {
  const api = read("lib/api.ts");
  assert.match(api, /export function useRecord[\s\S]*?\.\.\.opts, keepPreviousData: false \}/);
  assert.match(api, /const data = pickRecord\(requested, q\.data, idOf\)/);
});

test("every view that loads one record by id uses it", () => {
  const uses = {
    "components/ItemDrawer.tsx": /useRecord<ItemDetail>\(`\/api\/v1\/items\/\$\{encodeURIComponent\(id\)\}`, id, \(d\) => d\.item\?\.item_id\)/,
    "app/brief/page.tsx": /useRecord<ItemDetail>\([\s\S]*?id, \(d\) => d\.item\?\.item_id\)[\s\S]*|useRecord<Brief>\([\s\S]*?date, \(b\) => b\.date/,
    "app/competitors/[key]/page.tsx": /useRecord<CompetitorProfile>\([^\n]*key, \(d\) => d\.key\)/,
    "components/competitors/Matrix.tsx": /useRecord<CompetitorProfile>\([^\n]*keys\[i\], \(d\) => d\.key\)/,
    "components/competitors/HeadToHead.tsx": /useRecord<[\s\S]*?`\$\{who\}\/\$\{axis\}`, \(d\) => `\$\{d\.competitor\}\/\$\{d\.axis\}`\)/,
    "app/health/page.tsx": /useRecord<Health>\([\s\S]*?d\.run\?\.run_id/,
  };
  for (const [f, re] of Object.entries(uses)) assert.match(read(f), re, f);
  const brief = read("app/brief/page.tsx");
  assert.match(brief, /useRecord<Brief>\(/);
  for (const f of Object.keys(uses)) assert.doesNotMatch(read(f), /useApi<(ItemDetail|CompetitorProfile)>/, f);
});

test("the drawer's analyst actions only render with the matching record", () => {
  const drawer = read("components/ItemDrawer.tsx");
  assert.match(drawer, /<Async \{\.\.\.q\}[\s\S]*?\{\(d\) => \{[\s\S]*?<ReopenButton itemId=\{it\.item_id\}/);
});
