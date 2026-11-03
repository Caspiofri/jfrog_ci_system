// npm test: the "Reviewed by analyst" mark on Brief cards and Review rows (src/lib/reviewed.ts).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { REVIEWED_LABEL, reviewedHint } from "../src/lib/reviewed.ts";

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

test("the label and where it shows: Brief cards and Review rows, with the person icon and the hover", () => {
  assert.equal(REVIEWED_LABEL, "Reviewed by analyst");
  const mark = readFileSync(new URL("../src/components/ReviewedMark.tsx", import.meta.url), "utf8");
  assert.match(mark, /<UserCheck\b/);
  assert.match(mark, /title=\{hint\}/);
  for (const f of ["components/ItemRow.tsx", "components/brief/BriefCard.tsx"]) {
    assert.match(readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8"), /<ReviewedMark item=\{item\} \/>/, f);
  }
});
