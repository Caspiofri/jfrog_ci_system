// npm test: after Approve, a plain line says where the item went (D16, D31, D44). Display only.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { BELOW_BRIEF, approvedMessage } from "../src/lib/approvedWhere.ts";

const briefs = [{ date: "2026-11-01", anchor_run_id: "20261101T0400Z-e9cae4" }, { date: "2026-10-30", anchor_run_id: "20261030T1312Z-389e71" }];
const fmt = (d) => `<${d}>`;

test("3+ names the Brief of the item's run; below 3 points to the profile; otherwise just Approved.", () => {
  assert.equal(approvedMessage(4, "20261101T0400Z-e9cae4", briefs, fmt), "Approved. It appears in the Brief of <2026-11-01>.");
  assert.equal(approvedMessage(3, "20261030T1312Z-389e71", briefs, fmt), "Approved. It appears in the Brief of <2026-10-30>.");
  assert.equal(approvedMessage(2, "20261101T0400Z-e9cae4", briefs, fmt), BELOW_BRIEF);
  assert.equal(BELOW_BRIEF, "Approved. Scores below 3 appear on the competitor profile, not in the Brief.");
  assert.equal(approvedMessage(5, "20261102T0900Z-manual", briefs, fmt), "Approved.");
  assert.equal(approvedMessage(null, "20261101T0400Z-e9cae4", briefs, fmt), "Approved.");
});

test("only Approve reports it, at the top of the Review page, from fields the page already loads", () => {
  const a = readFileSync(new URL("../src/components/review/actions.tsx", import.meta.url), "utf8");
  assert.match(a, /\/approve`, \{\}, item\.version\), \(\) => onApproved\?\.\(item\)\)/);
  const p = readFileSync(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");
  assert.match(p, /approvedMessage\(it\.score, it\.run_id, briefs\.data\?\.items \?\? \[\], fmtLongDate\)/);
  assert.match(p, /\{approvedMsg \? <ApprovedNote text=\{approvedMsg\}/);
});
