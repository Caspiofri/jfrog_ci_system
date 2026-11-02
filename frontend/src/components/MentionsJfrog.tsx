"use client";
// The "Mentions JFrog" tag, with the excerpt sentence (when the excerpt names JFrog) on hover and keyboard focus.
import { Hint, Tag } from "@/components/ci";
import { mentionHint } from "@/lib/jfrogMention";

export function MentionsJfrog({ excerpt, strong = true }: { excerpt?: string | null; strong?: boolean }) {
  return (
    <Hint text={mentionHint(excerpt)}>
      <Tag className={strong ? "bg-[#eef7f0] font-semibold text-jgreen-d" : "bg-[#eef7f0] text-jgreen-d"}>Mentions JFrog</Tag>
    </Hint>
  );
}
