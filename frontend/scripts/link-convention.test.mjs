// npm test: one link convention on every screen. An item title opens the side drawer (ItemTitle);
// the only external link is ArticleLink (the publisher's name, D90, or "Source") with the external-link icon, opening the original page in a new tab.
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

const SRC = new URL("../src/", import.meta.url).pathname;
const files = (dir) => readdirSync(dir).flatMap((f) => {
  const p = join(dir, f);
  return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(f) ? [p] : [];
});
const APP = files(SRC).filter((p) => !p.includes("/components/ui/"));
const read = (p) => readFileSync(p, "utf8");

test("only ArticleLink opens a new tab", () => {
  const hits = APP.filter((p) => /target="_blank"/.test(read(p)));
  assert.deepEqual(hits.map((p) => p.replace(SRC, "")), ["components/ci.tsx"]);
  const ci = read(join(SRC, "components/ci.tsx"));
  assert.equal(ci.match(/target="_blank"/g).length, 1, "one external-link element in ci.tsx");
  assert.match(ci, /export function ArticleLink[\s\S]*?const text = name \?\? "Source";[\s\S]*?target="_blank"[\s\S]*?\{iconOnly \? null : <span[^>]*>\{text\}<\/span>\}\s*<ExternalLink/);
});

test("no other link style is left: no text link to an article, no chain-link or arrow icon", () => {
  for (const p of APP) {
    const s = read(p);
    assert.doesNotMatch(s, /<ExtLink\b/, `${p} still uses ExtLink`);
    assert.doesNotMatch(s, /\b(Link2|Link2Off|LinkIcon|Unlink)\b|🔗/, `${p} has a chain-link icon`);
    if (!p.endsWith("components/ci.tsx")) assert.doesNotMatch(s, /<ExternalLink\b/, `${p} draws its own external-link icon`);
    assert.doesNotMatch(s, /↗/, `${p} still shows the bare arrow`);
    assert.doesNotMatch(s, /Open the source</, `${p} still has a text link to the source`);
  }
});

test("every item list opens the drawer from the title and the article from the icon", () => {
  for (const f of ["components/ItemRow.tsx", "components/brief/BriefCard.tsx", "app/log/page.tsx", "components/competitors/parts.tsx"]) {
    const s = read(join(SRC, f));
    assert.match(s, /<ItemTitle\b[^>]*onOpen=\{/, `${f}: the title opens the drawer`);
  }
  assert.match(read(join(SRC, "components/ItemDrawer.tsx")), /<ArticleLink\b/, "the drawer has the Source control");
});

test("the icon is reachable by keyboard and named for screen readers", () => {
  const ci = read(join(SRC, "components/ci.tsx"));
  assert.match(ci, /ARTICLE_LINK_LABEL = "Open the original article in a new tab"/);
  assert.match(ci, /aria-label=\{aria\}/);
  assert.match(ci, /focus-visible:/);
});

test("insights: a claim card is not clickable; each cited article has a \"Reinforced by article\" button and one Source link", () => {
  const brief = read(join(SRC, "app/brief/page.tsx"));
  const claim = brief.slice(brief.indexOf("function ClaimBlock"), brief.indexOf("function SourceLine"));
  const line = brief.slice(brief.indexOf("function SourceLine"), brief.indexOf("\n}\n", brief.indexOf("function SourceLine")));
  assert.doesNotMatch(claim, /role="button"|onClick|onKeyDown|cursor-pointer/);
  assert.match(claim, /<li className="flex gap-2\.5 text-xs" data-claim-card>/, "no frame: no border, background or padding");
  assert.match(claim, /n=\{ids\.length > 1 \? k \+ 1 : null\}/, "numbered only when a claim cites several articles");
  assert.match(line, /<button type="button"[^>]*onClick=\{\(\) => drawer\.open\(id\)\}/);
  assert.match(line, /Reinforced by article\{n \? ` \$\{n\}` : ""\}/);
  assert.equal((line.match(/<button\b/g) ?? []).length, 1, "the score is no longer a second button");
  assert.doesNotMatch(line, /Source:|\{it\.title\}<|<ItemTitle/);
  assert.equal((line.match(/<ArticleLink\b/g) ?? []).length, 1);
});
