"use client";
// The drawer's "Where JFrog is mentioned" dropdown (D77), beside the article excerpt. Collapsed by default, like the
// excerpt. Shows the API's snippet as is, or says the mention isn't in the stored text. Not shown without the field.
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { MENTION_NOTE, MENTION_TITLE, NOT_IN_STORED_TEXT, mentionSection } from "@/lib/jfrogMention";
import type { JfrogMention } from "@/lib/types";

export function JfrogMentionSection({ mention }: { mention: JfrogMention | null | undefined }) {
  const [open, setOpen] = useState(false);
  const sec = mentionSection(mention);
  if (!sec) return null;
  return (
    <div className="flex flex-col gap-1" data-jfrog-mention>
      <button type="button" aria-expanded={open} onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className="inline-flex w-fit items-center gap-1 text-xs font-semibold text-jgreen-d hover:underline">
        {open ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
        {MENTION_TITLE}
      </button>
      {open ? (
        <div className="flex flex-col gap-1 rounded border border-line bg-page px-3 py-2">
          {sec.kind === "found" ? (
            <>
              <p className="m-0 text-[#44516a]">{sec.snippet}</p>
              <p className="m-0 text-[0.6875rem] text-mute">{MENTION_NOTE}{sec.inTitle ? " Found in the title." : ""}</p>
            </>
          ) : <p className="m-0 text-xs italic text-mute">{NOT_IN_STORED_TEXT}</p>}
        </div>
      ) : null}
    </div>
  );
}
