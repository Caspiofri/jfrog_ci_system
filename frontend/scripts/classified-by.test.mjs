// npm test: the drawer's "Classified by" line is a short plain label; the technical text is its hover.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { classifiedBy } from "../src/lib/classifiedBy.ts";

test("llm with a reason: \"AI model\", the full text on hover", () => {
  assert.deepEqual(classifiedBy({ method: "llm", reason: "ambiguous: two competitors named" }),
    { label: "AI model", hint: "llm · ambiguous: two competitors named" });
});

test("rules and the rule-based prefilter read \"rules\"", () => {
  assert.deepEqual(classifiedBy({ method: "rules" }), { label: "rules", hint: "rules" });
  assert.equal(classifiedBy({ method: "prefilter", reason: "x" }).label, "rules");
});

test("fallback says the model gave no usable answer, not AI model or rules", () => {
  const c = classifiedBy({ method: "fallback", reason: "LLM answer unusable (timeout); kept the prefilled competitor" });
  assert.equal(c.label, "AI model gave no usable answer");
  assert.equal(c.hint, "fallback · LLM answer unusable (timeout); kept the prefilled competitor");
});

test("no classification: a dash, no hover", () => {
  for (const c of [null, undefined, {}]) assert.deepEqual(classifiedBy(c), { label: "—", hint: null });
});

test("the drawer shows the label and puts the technical text in a hover", () => {
  const src = readFileSync(new URL("../src/components/ItemDrawer.tsx", import.meta.url), "utf8");
  assert.match(src, /<Field k="Classified by"><Hint text=\{cls\.hint\}>\{cls\.label\}<\/Hint><\/Field>/);
  assert.doesNotMatch(src, /classification\?\.method \?\? "—"/);
});
