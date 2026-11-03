// npm test: D90, the publisher's name on an article's external link instead of the generic "Source".
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { publisherName } from "../src/lib/format.ts";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("the stored publisher, as stored (real 1 Nov examples)", () => {
  assert.equal(publisherName("SecurityWeek", "https://www.securityweek.com/x"), "SecurityWeek");
  assert.equal(publisherName("The GitHub Blog", "https://github.blog/x"), "The GitHub Blog");
  assert.equal(publisherName("Amazon Web Services (AWS)", "https://aws.amazon.com/x"), "Amazon Web Services (AWS)");
});
test("aggregator, URL-shaped or missing publisher: the article's domain, never an invented name", () => {
  assert.equal(publisherName("Hacker News", "https://www.theregister.com/2026/10/30/x"), "theregister.com");
  assert.equal(publisherName("Google News", "https://news.example.org/a"), "news.example.org");
  assert.equal(publisherName("https://tech-insider.org/", "https://tech-insider.org/a"), "tech-insider.org");
  assert.equal(publisherName(null, "https://alpinelinux.org/posts/x"), "alpinelinux.org");
  assert.equal(publisherName("  ", "https://rushter.com/blog"), "rushter.com");
});
test("neither a publisher nor a usable URL: null, so the link keeps \"Source\"", () => {
  assert.equal(publisherName("Hacker News", "not a url"), null);
  assert.equal(publisherName(null, null), null);
});
test("the link shows the name on one line, full name on hover, with the external-link icon", () => {
  const ci = src("components/ci.tsx");
  assert.match(ci, /const name = publisher !== undefined \? publisherName\(publisher, safe\) : null;/);
  assert.match(ci, /<span className=\{name \? "max-w-\[14rem\] truncate" : undefined\}>\{text\}<\/span>\}\s*<ExternalLink/);
  assert.match(ci, /title=\{name \? `\$\{name\} · \$\{aria\}`/);
});
test("Brief, Review (item rows), Log, drawer and insight citations pass the publisher", () => {
  assert.match(src("components/brief/BriefCard.tsx"), /<ItemTitle [^>]*publisher=\{item\.publisher\}/);
  assert.match(src("components/ItemRow.tsx"), /<ItemTitle [^>]*publisher=\{item\.publisher\}/);
  assert.match(src("app/log/page.tsx"), /<ItemTitle [^>]*publisher=\{r\.publisher\}/);
  assert.match(src("components/ItemDrawer.tsx"), /<ArticleLink href=\{q\.data\.item\.url\} publisher=\{q\.data\.item\.publisher\}/);
  assert.match(src("components/ArticleExcerpt.tsx"), /publisher=\{publisher \?\? null\}/);
  assert.match(src("app/brief/page.tsx"), /<ArticleLink href=\{it\.url\} publisher=\{it\.publisher\} \/>/);
});
