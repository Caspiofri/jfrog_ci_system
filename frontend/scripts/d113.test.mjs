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

test("the header stays fixed with the nav; anchors land below it; logo and header content unchanged", () => {
  const sh = src("components/shell/Shell.tsx");
  assert.match(sh, /<div ref=\{head\} className="sticky top-0 z-40 col-span-full" data-fixed-head>\s*<header className="flex h-14 items-center gap-3\.5 bg-navy px-5 text-\[#e8edf5\]">/);
  assert.match(sh, /<Image src="\/brand\/jessi-mark\.svg" alt="Jessi" width=\{132\} height=\{40\} priority unoptimized className="h-10 w-auto" \/>/);
  assert.match(sh, /<\/header>\s*<DemoLine \/>\s*<\/div>/); // the demo line stays fixed with the header
  // narrow: the nav row sticks under the header; wide: the sidebar nav sticks below it
  assert.match(sh, /<aside ref=\{nav\} className="sticky top-\[var\(--head-h,3\.5rem\)\] z-30 [^"]* md:static md:z-auto"/);
  assert.match(sh, /<nav aria-label="Screens" className="flex [^"]*md:sticky md:top-\[calc\(var\(--head-h,3\.5rem\)\+0\.5rem\)\]/);
  assert.match(sh, /setProperty\("--head-h"/);
  assert.match(sh, /getComputedStyle\(n\)\.position === "sticky" \? n\.offsetHeight : 0/);
  const css = src("app/globals.css");
  assert.match(css, /scroll-padding-top: calc\(var\(--head-h, 3\.5rem\) \+ var\(--nav-h, 0px\) \+ 0\.5rem\);/);
});

test("the four tiles share one top-aligned box, so label and number sit at the same height in each", () => {
  const b = src("app/brief/page.tsx");
  assert.match(b, /const box = "flex flex-col justify-start rounded-md border border-line bg-card px-4 py-3 text-left";/);
  // every tile uses that box: the Needs review link, the two scroll buttons and the plain tiles
  assert.match(b, /<Link href=\{`\/review\?brief=[^>]*className=\{cn\(box, /);
  assert.match(b, /<button type="button" data-tile=\{t\.key\} className=\{cn\(box, /);
  assert.match(b, /className=\{box\}><span data-tile=\{t\.key\}>\{body\}<\/span><\/Hint>/);
  // "Review these" stays under the number, inside the same tile body
  assert.match(b, /\{t\.value \?\? [^}]*\}\s*<\/b>\s*\{t\.key === "review" && t\.value \? \(\s*<span [^>]*>[\s\S]*?Review these<\/span>/);
});
