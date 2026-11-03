// The "Edited by analyst" mark (D94): pencil icon and label, only when an analyst edited the item; the hover says what
// the analyst did (src/lib/reviewed.ts). It never reads as a decision: approvals and flags show in the status.
import { Pencil } from "lucide-react";
import { Tag } from "@/components/ci";
import { REVIEWED_LABEL, editedFields, reviewedHint, type ReviewedFields } from "@/lib/reviewed";

export function ReviewedMark({ item }: { item: ReviewedFields }) {
  const hint = reviewedHint(item);
  if (!hint || !editedFields(item).length) return null;
  return (
    <Tag className="inline-flex items-center gap-1 border border-line bg-white text-[#44516a]" title={hint}>
      <Pencil className="size-3" aria-hidden />
      {REVIEWED_LABEL}
    </Tag>
  );
}
