// npm test: D94 terminology, display text only. "Published" is gone from the screens: "Article date" (the publisher's
// date), "Collected" (when our pipeline found it) and "Cleared" (passed routing, or approved by an analyst).
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { ARTICLE_DATE_TIP, CLEARED_TIP, COLLECTED_TIP, STATUS_LABEL, routeReasonWords } from "../src/lib/format.ts";

const root = new URL("../src/", import.meta.url).pathname;
const files = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? (p.includes("components/ui") ? [] : files(p)) : /\.(tsx|ts)$/.test(p) && !/mock\.ts$|types\.ts$/.test(p) ? [p] : []; });
// visible text: string literals and JSX text, with comments removed; identifiers such as auto_published stay out
const visible = (s) => s.replace(/\/\*[\s\S]*?\*\/|(^|[^:])\/\/.*$/gm, "$1").replace("/^published at\\b/", ""); // the one regex that maps the API's reason

test("the three terms and their hovers, as written", () => {
  assert.equal(ARTICLE_DATE_TIP, "The date the publisher put on the article.");
  assert.equal(COLLECTED_TIP, "When our pipeline found it.");
  assert.equal(CLEARED_TIP, "Passed routing, or approved by an analyst.");
  assert.equal(STATUS_LABEL.auto_published, "Cleared");
});

test("no screen says published or feed date", () => {
  for (const f of files(root)) {
    const s = visible(readFileSync(f, "utf8"));
    const bad = s.match(/(?<![\w_."])(?:[Pp]ublished|[Ff]eed date)(?![\w_"?]|:)|"[^"]*[^"\w][Pp]ublished"/g);
    assert.equal(bad, null, `${f.replace(root, "")}: ${bad}`);
  }
});

test("no status or tile is named Verified or Checked, and held items are not called unverified", () => {
  for (const v of Object.values(STATUS_LABEL)) assert.doesNotMatch(v, /verified|checked/i);
  for (const f of files(root)) assert.doesNotMatch(visible(readFileSync(f, "utf8")), /not verified|aren't verified|unverified item/i, f);
});

test("the heatmap is \"Cleared items by category\"", () => {
  assert.match(readFileSync(join(root, "components/competitors/Heatmap.tsx"), "utf8"), /<Panel title="Cleared items by category"/);
});

test("the Log's route reason reads cleared (the API still stores published at <level>)", () => {
  assert.equal(routeReasonWords("published at strict"), "cleared at strict");
  assert.equal(routeReasonWords("unvetted_source"), "unvetted_source");
  assert.equal(routeReasonWords(null), "");
  assert.match(readFileSync(join(root, "app/log/page.tsx"), "utf8"), /routeReasonWords\(r\.reason\)/);
});
