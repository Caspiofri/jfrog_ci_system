// npm test: "From the article" on Brief cards and in the drawer: collapsed by default, text as served.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const ex = read("components/ArticleExcerpt.tsx");
const card = read("components/brief/BriefCard.tsx");
const drawer = read("components/ItemDrawer.tsx");

test("labelled 'From the article', collapsed by default behind 'Show excerpt'", () => {
  assert.match(ex, /EXCERPT_LABEL = "From the article"/);
  assert.match(ex, /const \[open, setOpen\] = useState\(false\)/);
  assert.match(ex, /\{open \? "Hide excerpt" : "Show excerpt"\}/);
  assert.match(ex, /\{open \? <span className="[^"]*">\{excerpt\}<\/span> : null\}/);
});

test("the toggle is a real button with aria-expanded, and doesn't trigger the card behind it", () => {
  assert.match(ex, /<button type="button" aria-expanded=\{open\} onClick=\{\(e\) => \{ e\.stopPropagation\(\); setOpen\(!open\); \}\}/);
});

test("the text is shown as served: not stripped, shortened or rewritten", () => {
  const body = ex.slice(ex.indexOf("export function ArticleExcerpt"));
  assert.doesNotMatch(body, /\.(replace|slice|substring|split)\(/);
  assert.match(ex, /NO_EXCERPT = "Only the headline is available\."/);
});

test("Brief card: 'From the article' replaces 'What happened'; title, Why it matters (when it exists) and Evidence stay visible", () => {
  assert.doesNotMatch(card + drawer, /What happened/);
  assert.match(card, /<Row label=\{EXCERPT_LABEL\}><ArticleExcerpt excerpt=\{item\.excerpt\} \/><\/Row>/);
  assert.match(card, /\{showLensBlock\(item\.lens, item\.lens_status\) \? \(\s*<Row label="Why it matters to JFrog">/);
  assert.match(card, /<Row label="Evidence">/);
  assert.match(card, /<ItemTitle title=\{item\.title\}/);
});

test("drawer: the same collapsed excerpt under 'From the article'", () => {
  assert.match(drawer, /\{EXCERPT_LABEL\}<\/div>\s*<ArticleExcerpt excerpt=\{it\.excerpt\} \/>/);
});
