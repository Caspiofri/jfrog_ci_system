// npm test: browser extensions (e.g. Grammarly) add attributes to <body> before React loads; only <body>'s own
// attribute mismatch is ignored, so real hydration errors inside the page still show.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("<body> ignores attributes added by browser extensions, nothing wider", () => {
  const src = readFileSync(new URL("../src/app/layout.tsx", import.meta.url), "utf8");
  assert.match(src, /<body className=\{`\$\{openSans\.variable\} font-sans antialiased`\} suppressHydrationWarning>/);
  assert.equal(src.match(/suppressHydrationWarning/g).length, 1);
});
