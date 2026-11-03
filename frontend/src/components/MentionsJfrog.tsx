"use client";
// The "Mentions JFrog" tag, with the excerpt sentence (when the excerpt names JFrog) on hover and keyboard focus.
import { Hint, Tag } from "@/components/ci";
import { mentionHint } from "@/lib/jfrogMention";
import type { JfrogMention } from "@/lib/types";

export function MentionsJfrog({ excerpt, mention, strong = true }: { excerpt?: string | null; mention?: JfrogMention | null; strong?: boolean }) {
  return (
    <Hint text={mentionHint(excerpt, mention)}>
      <Tag className={strong ? "bg-[#eef7f0] font-semibold text-jgreen-d" : "bg-[#eef7f0] text-jgreen-d"}>Mentions JFrog</Tag>
    </Hint>
  );
}
