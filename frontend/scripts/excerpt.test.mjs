// npm test: Brief cards keep "What happened" visible; the drawer has the article dropdown, the JFrog mention and tag.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const ex = read("components/ArticleExcerpt.tsx");
const card = read("components/brief/BriefCard.tsx");
const drawer = read("components/ItemDrawer.tsx");

test("Brief card: the earlier design: 'What happened' with the excerpt visible, 'Why it matters to JFrog' on every card", () => {
  assert.match(card, /<Row label="What happened">\s*\{item\.excerpt\.trim\(\) \? <span className="[^"]*">\{item\.excerpt\}<\/span>/);
  assert.match(card, /<Row label="Why it matters to JFrog"><LensView lens=\{item\.lens\} status=\{item\.lens_status\} \/><\/Row>/);
  assert.match(card, /<Row label="Evidence">/);
  assert.doesNotMatch(card, /ArticleExcerpt|Show excerpt|showLensBlock/);
});

test("drawer: the article dropdown, collapsed by default, holds the excerpt and the Source link", () => {
  assert.match(ex, /const \[open, setOpen\] = useState\(false\)/);
  assert.match(ex, /SHOW_LABEL = "Show article excerpt"/);
  assert.match(ex, /<button type="button" aria-expanded=\{open\}/);
  assert.match(ex, /\{open \? \([\s\S]*?\{excerpt\}[\s\S]*?<ArticleLink href=\{url\}/);
  assert.match(drawer, /<ArticleExcerpt excerpt=\{it\.excerpt\} url=\{it\.url\} publisher=\{it\.publisher\} \/>/);
});

test("the excerpt is shown as served: not stripped, shortened or rewritten", () => {
  const body = ex.slice(ex.indexOf("export function ArticleExcerpt"));
  assert.doesNotMatch(body, /\.(replace|slice|substring|split)\(/);
});

test("drawer: the 'Why Mentions JFrog' block and the Brief's 'Mentions JFrog' tag", () => {
  assert.match(drawer, /<MentionWhy d=\{d\} \/>/);
  assert.match(drawer, /const m = mentionExplanation\(d\);\s*if \(!m\) return null;/);
  assert.match(drawer, /\{it\.mentions_jfrog \? <MentionsJfrog excerpt=\{it\.excerpt\} mention=\{it\.jfrog_mention\} \/> : null\}/);
  assert.match(card, /<MentionsJfrog excerpt=\{item\.excerpt\} mention=\{item\.jfrog_mention\} \/>/);
});
