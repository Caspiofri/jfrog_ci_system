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

import { mentionExplanation } from "../src/lib/jfrogMention.ts";

// item a3e6628ceeb10e86 as GET /items/{id} serves it (1 Nov demo and live): flag set, excerpt without the name
const WORM = {
  item: {
    title: "Worm armed 42 GitHub repos by hiding a payload too big to fail",
    excerpt: "security Worm armed 42 GitHub repos by hiding a payload too big to fail Payload blobs measuring 12.9 to 13.7 MB were large enough to evade GitHub code search A new Miasma-family npm worm…",
    why_it_matters: "Validates the need for package security tools and highlights research from JFrog's security team.",
    mentions_jfrog: true,
    hold_reasons: [{ code: "mentions_jfrog", held_at: ["strict", "balanced", "relaxed"] }],
  },
  ranking: { raw_score: 3, adjustments: ["+1 Mentions JFrog"] },
};

test("why tagged, when the mention is in the article body only (the reported item)", () => {
  const m = mentionExplanation(WORM);
  assert.equal(m.sentence, null);
  assert.match(m.how, /text match found the name JFrog in the article text the system read/);
  assert.match(m.how, /first 280 characters, which don't include the mention/);
  assert.deepEqual(m.effect, ["Score raised by 1 for mentioning JFrog (3 → 4).", "Held for an analyst at every autonomy level."]);
  assert.equal(m.modelNote, WORM.item.why_it_matters);
});

test("why tagged, when the excerpt or the title holds the name", () => {
  const ex = mentionExplanation({ ...WORM, item: { ...WORM.item, excerpt: "Intro. JFrog researchers found it. More." } });
  assert.equal(ex.sentence, "JFrog researchers found it.");
  assert.match(ex.how, /sentence below/);
  const ti = mentionExplanation({ ...WORM, item: { ...WORM.item, title: "JFrog finds a worm" } });
  assert.equal(ti.how, "The title names JFrog.");
});

test("no tag: no block; no adjustment or hold: no effect lines; a model note without JFrog isn't shown", () => {
  assert.equal(mentionExplanation({ item: { ...WORM.item, mentions_jfrog: false } }), null);
  const m = mentionExplanation({ item: { ...WORM.item, hold_reasons: [], why_it_matters: "Package security matters." }, ranking: { raw_score: 3, adjustments: [] } });
  assert.deepEqual(m.effect, []);
  assert.equal(m.modelNote, null);
});
