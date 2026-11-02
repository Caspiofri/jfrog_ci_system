// "Reviewed by analyst": an item an analyst approved, edited or flagged. Read from the list row itself (status,
// edited, flagged), so no extra request. The analyst's note stays in the side panel's history. No imports.
export const REVIEWED_LABEL = "Reviewed by analyst";

export interface ReviewedFields { status: string; edited: Record<string, unknown> | null; flagged: boolean }

/** The hover for the mark, e.g. "Edited by an analyst (score, competitor)"; null when no analyst touched the item. */
export function reviewedHint(it: ReviewedFields): string | null {
  const fields = Object.keys(it.edited ?? {});
  const parts: string[] = [];
  if (it.status === "approved") parts.push("approved");
  if (fields.length) parts.push("edited");
  if (it.flagged || it.status === "flagged") parts.push("flagged");
  if (!parts.length) return null;
  const said = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return `${said[0].toUpperCase()}${said.slice(1)} by an analyst${fields.length ? ` (${fields.join(", ")})` : ""}`;
}
