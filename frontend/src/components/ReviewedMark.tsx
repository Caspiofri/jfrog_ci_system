// The "Reviewed by analyst" mark: person icon and label, the hover says what the analyst did (src/lib/reviewed.ts).
import { UserCheck } from "lucide-react";
import { Tag } from "@/components/ci";
import { REVIEWED_LABEL, reviewedHint, type ReviewedFields } from "@/lib/reviewed";

export function ReviewedMark({ item }: { item: ReviewedFields }) {
  const hint = reviewedHint(item);
  if (!hint) return null;
  return (
    <Tag className="inline-flex items-center gap-1 border border-line bg-white text-[#44516a]" title={hint}>
      <UserCheck className="size-3" aria-hidden />
      {REVIEWED_LABEL}
    </Tag>
  );
}
