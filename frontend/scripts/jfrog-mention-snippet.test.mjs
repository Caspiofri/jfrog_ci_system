// npm test: "Where JFrog is mentioned" (D77) from Item.jfrog_mention, mock items in the contract's shape.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { MENTION_NOTE, MENTION_TITLE, NOT_IN_STORED_TEXT, mentionHint, mentionSection } from "../src/lib/jfrogMention.ts";

const FOUND = { status: "found", snippet: "…according to JFrog researchers. Threat hunters…", found_in: "text" };
const IN_TITLE = { status: "found", snippet: "Snyk and JFrog team up", found_in: "title" };
const NOT_STORED = { status: "not_in_stored_text", snippet: null, found_in: null };
const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

test("labels: a mention, not a comparison", () => {
  assert.equal(MENTION_TITLE, "Where JFrog is mentioned");
  assert.match(MENTION_NOTE, /mention.*not a comparison/i);
});

test("found: the snippet as given, and where it was found", () => {
  assert.deepEqual(mentionSection(FOUND), { kind: "found", snippet: FOUND.snippet, inTitle: false });
  assert.deepEqual(mentionSection(IN_TITLE), { kind: "found", snippet: IN_TITLE.snippet, inTitle: true });
});

test("not in the stored text: an explicit message, never a blank", () => {
  assert.deepEqual(mentionSection(NOT_STORED), { kind: "not_in_stored_text" });
  assert.match(NOT_IN_STORED_TEXT, /not in the part of the article we store/);
});

test("no field (older snapshot) or an unknown status: no section", () => {
  for (const m of [undefined, null, { status: "other" }, { status: "found", snippet: "  " }]) assert.equal(mentionSection(m), null);
});

test("the chip's hover uses the snippet when found, else the excerpt sentence as before", () => {
  assert.equal(mentionHint("No match here.", FOUND), `Mentioned: “${FOUND.snippet}”`);
  assert.equal(mentionHint("JFrog Artifactory was named. Other text.", NOT_STORED), "In the excerpt: “JFrog Artifactory was named.”");
  assert.equal(mentionHint(null, undefined), "The article text mentions JFrog.");
});

test("drawer shows the section; cards and rows pass the mention to the chip", () => {
  const drawer = read("../src/components/ItemDrawer.tsx");
  assert.match(drawer, /<ArticleExcerpt excerpt=\{it\.excerpt\} url=\{it\.url\} \/>\s*<JfrogMentionSection mention=\{it\.jfrog_mention\} \/>/);
  for (const p of ["../src/components/brief/BriefCard.tsx", "../src/components/ItemRow.tsx"]) {
    assert.match(read(p), /<MentionsJfrog excerpt=\{item\.excerpt\} mention=\{item\.jfrog_mention\} \/>/, p);
  }
  assert.match(drawer, /<MentionsJfrog excerpt=\{it\.excerpt\} mention=\{it\.jfrog_mention\} \/>/);
  assert.match(read("../src/lib/types.ts"), /jfrog_mention\?: JfrogMention \| null;/);
});
