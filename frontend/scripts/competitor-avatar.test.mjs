// npm test: competitor monogram avatars, one colour per competitor everywhere (src/lib/competitors.ts).
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { COMPETITOR_COLOR, OTHER_COLOR, competitorColor, monogram } from "../src/lib/competitors.ts";

const TRACKED = ["cloudsmith", "sonatype", "github", "gitlab", "snyk", "aws"]; // GET /meta, not Industry

test("a letter monogram from the display name", () => {
  assert.equal(monogram("GitHub"), "G");
  assert.equal(monogram("AWS"), "A");
  assert.equal(monogram("Sonatype"), "S");
  assert.equal(monogram("", "snyk"), "S");
  assert.equal(monogram(null, null), "?");
});

test("each tracked competitor has its own colour", () => {
  const colours = TRACKED.map((k) => competitorColor(k));
  assert.equal(new Set(colours).size, TRACKED.length);
  for (const c of colours) assert.notEqual(c, OTHER_COLOR);
});

test("unknown keys fall back to one neutral colour, not an error", () => {
  assert.equal(competitorColor("someone_new"), OTHER_COLOR);
  assert.equal(competitorColor(null), OTHER_COLOR);
  assert.equal(competitorColor(undefined), OTHER_COLOR);
});

// WCAG relative luminance: white text on each colour must reach 4.5:1.
const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
test("white letters are readable on every colour (contrast >= 4.5)", () => {
  for (const [k, c] of Object.entries(COMPETITOR_COLOR)) assert.ok(1.05 / (lum(c) + 0.05) >= 4.5, `${k} ${c}`);
});

const SRC = new URL("../src/", import.meta.url).pathname;
const files = (dir) => readdirSync(dir).flatMap((f) => {
  const p = join(dir, f);
  return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(f) ? [p] : [];
});

test("no company logo is fetched or embedded", () => {
  for (const p of files(SRC)) {
    const s = readFileSync(p, "utf8");
    assert.doesNotMatch(s, /clearbit|brandfetch|logo\.dev|favicon|logos?\.(png|svg|jpe?g|webp)|<img\b/i, p);
  }
});

test("the avatar's colour comes only from the shared map", () => {
  const av = readFileSync(join(SRC, "components/CompetitorAvatar.tsx"), "utf8");
  assert.match(av, /competitorColor\(k\)/);
  assert.match(av, /aria-label=\{n\}/);
});
