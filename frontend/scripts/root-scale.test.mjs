// npm test: D89 layout. The root font size grows with the viewport (clamp, no fixed zoom), and app sizes are in rem,
// so they grow with it; the main column has a reading limit, not a narrow fixed width.
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

const root = new URL("../src/", import.meta.url).pathname;
const files = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? (p.includes("components/ui") ? [] : files(p)) : p.endsWith(".tsx") ? [p] : []; });

test("root font size: clamp from 100% to 125% by viewport width, no zoom", () => {
  const css = readFileSync(join(root, "app/globals.css"), "utf8");
  assert.match(css, /html \{\s*font-size: clamp\(100%, [^)]*vw, 125%\);/);
  assert.doesNotMatch(css, /\bzoom\s*:/);
  assert.doesNotMatch(css, /text-\[\d+px\]/);
});

test("no px text, padding, gap or size utilities in app code (they would not grow)", () => {
  for (const f of files(root)) {
    const bad = readFileSync(f, "utf8").match(/(?<![\w-])(?:text|px|py|p|gap|size|min-w|h|grid-rows|grid-cols)-\[[^\]]*\b(?:[5-9]|\d{2,})px[^\]]*\]/g);
    assert.equal(bad, null, `${f}: ${bad}`);
  }
});

test("main column uses the screen, with a reading limit", () => {
  assert.match(readFileSync(join(root, "components/shell/Shell.tsx"), "utf8"), /<main className="mx-auto flex w-full min-w-0 max-w-\[110rem\]/);
});
