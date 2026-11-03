// npm test: the "Edited by analyst" mark (D94; was "Reviewed by analyst") on Brief cards and Review rows (src/lib/reviewed.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { REVIEWED_LABEL, editedFields, reviewedHint } from "../src/lib/reviewed.ts";

const base = { status: "auto_published", edited: null, flagged: false };

test("no analyst action: no mark (auto-published, awaiting review, held)", () => {
  assert.equal(reviewedHint(base), null);
  assert.equal(reviewedHint({ ...base, status: "awaiting_review" }), null);
  assert.equal(reviewedHint({ ...base, edited: {} }), null, "an empty edit is not an edit");
});

test("approved, edited (with the fields) or flagged each give the mark, and the hover says which", () => {
  assert.equal(reviewedHint({ ...base, status: "approved" }), "Approved by an analyst");
  assert.equal(reviewedHint({ ...base, edited: { score: 3, competitor: "none" } }), "Edited by an analyst (score, competitor)");
  assert.equal(reviewedHint({ ...base, flagged: true }), "Flagged by an analyst");
  assert.equal(reviewedHint({ ...base, status: "flagged" }), "Flagged by an analyst");
  assert.equal(reviewedHint({ status: "approved", edited: { category: "Security" }, flagged: true }),
    "Approved, edited and flagged by an analyst (category)");
});

test("the mark shows only for an edit, never for an approval or a flag alone (it must not read as a decision)", () => {
  assert.deepEqual(editedFields({ edited: { competitor: "industry", score: 4 } }), ["competitor", "score"]);
  assert.deepEqual(editedFields({ edited: null }), []);
  const mark = readFileSync(new URL("../src/components/ReviewedMark.tsx", import.meta.url), "utf8");
  assert.match(mark, /if \(!hint \|\| !editedFields\(item\)\.length\) return null;/);
});

test("the label and where it shows: Brief cards and Review rows, with the pencil icon and the hover", () => {
  assert.equal(REVIEWED_LABEL, "Edited by analyst");
  const mark = readFileSync(new URL("../src/components/ReviewedMark.tsx", import.meta.url), "utf8");
  assert.match(mark, /<Pencil\b/);
  assert.doesNotMatch(mark, /UserCheck/);
  assert.match(mark, /title=\{hint\}/);
  for (const f of ["components/ItemRow.tsx", "components/brief/BriefCard.tsx"]) {
    assert.match(readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8"), /<ReviewedMark item=\{item\} \/>/, f);
  }
});
