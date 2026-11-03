"use client";
// The drawer's article dropdown: the first 280 characters of the page as the API serves them (the API never sends
// the full article), with the "Source" link to the full article. Collapsed by default; the text is shown as is.
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { ArticleLink } from "@/components/ci";

export const SHOW_LABEL = "Show article excerpt";
export const HIDE_LABEL = "Hide article excerpt";
export const NO_EXCERPT = "Only the headline is available.";

export function ArticleExcerpt({ excerpt, url, publisher }: { excerpt: string | null | undefined; url?: string | null; publisher?: string | null }) {
  const [open, setOpen] = useState(false); // collapsed by default
  return (
    <div className="flex flex-col gap-1" data-excerpt>
      <button type="button" aria-expanded={open} onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className="inline-flex w-fit items-center gap-1 text-xs font-semibold text-jgreen-d hover:underline">
        {open ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
        {open ? HIDE_LABEL : SHOW_LABEL}
      </button>
      {open ? (
        <div className="flex flex-col gap-1 rounded border border-line bg-page px-3 py-2">
          {excerpt?.trim() ? <p className="m-0 text-[#44516a]">{excerpt}</p> : <p className="m-0 text-xs italic text-mute">{NO_EXCERPT}</p>}
          <ArticleLink href={url} label="Open the full article in a new tab" publisher={publisher ?? null} />
        </div>
      ) : null}
    </div>
  );
}
