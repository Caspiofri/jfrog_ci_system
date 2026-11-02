"use client";
// "From the article": the first 280 characters of the page as the API serves them (no model summary exists).
// Sometimes page boilerplate, so collapsed by default behind "Show excerpt". The text is shown as is.
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

export const EXCERPT_LABEL = "From the article";
export const NO_EXCERPT = "Only the headline is available.";

export function ArticleExcerpt({ excerpt }: { excerpt: string | null | undefined }) {
  const [open, setOpen] = useState(false); // collapsed by default
  if (!excerpt?.trim()) return <span className="text-xs text-mute">{NO_EXCERPT}</span>;
  return (
    <span className="flex flex-col gap-1" data-excerpt>
      <button type="button" aria-expanded={open} onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className="inline-flex w-fit items-center gap-1 text-xs font-semibold text-jgreen-d hover:underline">
        {open ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
        {open ? "Hide excerpt" : "Show excerpt"}
      </button>
      {open ? <span className="text-[#44516a]">{excerpt}</span> : null}
    </span>
  );
}
