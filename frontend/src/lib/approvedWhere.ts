// After Approve, say where the item went (D16, D31, D44): scored 3+ it joins the Brief of its discovery window;
// below 3 it goes to the competitor profile. Only fields the Review page already has: the item's score and run_id,
// and GET /briefs (each Brief's date and anchor run). An item from a run that anchors no Brief gets "Approved." only.

export const BRIEF_MIN_SCORE = 3;
export const BELOW_BRIEF = "Approved. Scores below 3 appear on the competitor profile, not in the Brief.";

export function approvedMessage(
  score: number | null | undefined,
  runId: string | null | undefined,
  briefs: { date: string; anchor_run_id?: string | null }[],
  fmt: (date: string) => string,
): string {
  if (score == null) return "Approved.";
  if (score < BRIEF_MIN_SCORE) return BELOW_BRIEF;
  const b = runId ? briefs.find((x) => x.anchor_run_id === runId) : undefined;
  return b ? `Approved. It appears in the Brief of ${fmt(b.date)}.` : "Approved.";
}
