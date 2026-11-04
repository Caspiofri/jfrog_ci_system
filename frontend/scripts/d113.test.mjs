// npm test: D113, the last display-only round. Text and links only; no API, stored data, score or number changes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { splitJfrog } from "../src/lib/jfrogMention.ts";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("splitJfrog marks JFrog in any letter case and gives the text back unchanged", () => {
  const t = "JFrog and jfrog, JFROG; Jfrog's <b>x</b> frog";
  const parts = splitJfrog(t);
  assert.equal(parts.map((p) => p.text).join(""), t);
  assert.deepEqual(parts.filter((p) => p.jfrog).map((p) => p.text), ["JFrog", "jfrog", "JFROG", "Jfrog"]);
  assert.ok(parts.filter((p) => !p.jfrog).every((p) => !/jfrog/i.test(p.text)));
  assert.deepEqual(splitJfrog("no mention"), [{ text: "no mention", jfrog: false }]);
  assert.deepEqual(splitJfrog(""), []);
});

test("the mention section renders the pieces as React text, green, never as HTML", () => {
  const c = src("components/JfrogMentionSection.tsx");
  assert.match(c, /splitJfrog\(sec\.snippet\)\.map\(\(p, i\) => \(p\.jfrog \? <mark [^>]*text-jgreen-d[^>]*>\{p\.text\}<\/mark> : <span key=\{i\}>\{p\.text\}<\/span>\)\)/);
  assert.doesNotMatch(c, /dangerouslySetInnerHTML/);
});

test("Brief: 'Items in this Brief'; Cleared and High score scroll to the cleared list without touching filters", () => {
  const b = src("app/brief/page.tsx");
  assert.match(b, />Items in this Brief\{s\.mock/);
  assert.match(b, /id=\{CLEARED_ID\}\s*title="What was cleared in this Brief\?"/);
  const m = b.match(/t\.key === "published" \|\| t\.key === "high" \? \([\s\S]*?<\/Hint>/);
  assert.ok(m, "the two tiles have their own branch");
  assert.match(m[0], /<button type="button"[\s\S]*document\.getElementById\(CLEARED_ID\)\?\.scrollIntoView/);
  assert.doesNotMatch(m[0], /set\(|router|href=/);
});
