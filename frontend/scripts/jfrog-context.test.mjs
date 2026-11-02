// npm test: JFrog context in Review and the drawer (src/lib/jfrogMention.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { MENTION_FALLBACK, jfrogSentence, mentionHint, showLensBlock } from "../src/lib/jfrogMention.ts";

test("no lens result: the 'Why it matters to JFrog' block is not shown", () => {
  assert.equal(showLensBlock(null, null), false);
  assert.equal(showLensBlock(undefined, undefined), false);
});

test("a lens result, or a lens that failed, keeps the block (so a failure is never hidden)", () => {
  assert.equal(showLensBlock({ axis: "ai_mcp" }, "ok"), true);
  assert.equal(showLensBlock(null, "rejected"), true);
  assert.equal(showLensBlock(null, "failed"), true);
});

test("Mentions JFrog: the excerpt's sentence when it names JFrog", () => {
  const ex = "Attackers hit 42 repos. JFrog Security Research found the malware in npm packages. More to come.";
  assert.equal(jfrogSentence(ex), "JFrog Security Research found the malware in npm packages.");
  assert.equal(mentionHint(ex), "In the excerpt: “JFrog Security Research found the malware in npm packages.”");
  assert.equal(jfrogSentence("…as jfrog's report said"), "as jfrog's report said");
});

test("Mentions JFrog: a plain statement when the excerpt doesn't name JFrog (never a guess)", () => {
  for (const ex of ["Nothing about it here.", "", null, undefined]) {
    assert.equal(jfrogSentence(ex), null);
    assert.equal(mentionHint(ex), MENTION_FALLBACK);
  }
  assert.equal(MENTION_FALLBACK, "The article text mentions JFrog.");
});

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the drawer and the Review rows use them; no new API call", () => {
  const drawer = read("components/ItemDrawer.tsx");
  assert.match(drawer, /\{showLensBlock\(it\.lens, it\.lens_status\) \? <LensBlock/);
  assert.match(drawer, /<MentionsJfrog excerpt=\{it\.excerpt\}/);
  assert.match(read("components/ItemRow.tsx"), /<MentionsJfrog excerpt=\{item\.excerpt\} \/>/);
  const comp = read("components/MentionsJfrog.tsx") + read("lib/jfrogMention.ts");
  assert.doesNotMatch(comp, /useApi|fetch\(|\/api\/v1/);
  assert.match(read("components/MentionsJfrog.tsx"), /<Hint text=\{mentionHint\(excerpt\)\}>/);
});
