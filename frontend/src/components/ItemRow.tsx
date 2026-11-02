"use client";
// One item in a list (prototype .row with r5/r4/r3 emphasis). Title opens the drawer; the icon opens the source.
import { MentionsJfrog } from "@/components/MentionsJfrog";
import { CompetitorLabel } from "@/components/CompetitorAvatar";
import type { ReactNode } from "react";
import { CategoryTag, ItemTitle, ScoreBadge, Tag, openFromRow } from "@/components/ci";
import { ReviewedMark } from "@/components/ReviewedMark";
import { useItemDrawer } from "@/components/ItemDrawer";
import { NO_TEXT, itemDateText } from "@/lib/format";
import type { Item } from "@/lib/types";
import { cn } from "@/lib/utils";

const EMPHASIS: Record<number, string> = {
  5: "bg-[#fff1f0] border-l-4 border-l-[#9b1c1c] px-2.5",
  4: "bg-[#fff7f6] border-l-4 border-l-[#e5483b] px-2.5",
  3: "border-l-4 border-l-[#f59e0b] pl-2.5",
};

export function ItemRow({ item, showBadge = true, highlight = false, actions, extra }: {
  item: Item;
  showBadge?: boolean;
  highlight?: boolean;
  actions?: ReactNode;
  extra?: ReactNode;
}) {
  const drawer = useItemDrawer();
  const s = item.noise ? 0 : (item.score ?? 0);
  return (
    <div
      className={cn(
        "flex cursor-pointer items-start gap-3 border-t border-line py-2.5 first:border-t-0 hover:bg-page/60",
        EMPHASIS[s],
        s > 0 && s <= 2 && "opacity-80",
        highlight && "ring-2 ring-jgreen ring-inset bg-[#f3fbf4]",
      )}
      data-item={item.item_id}
      onClick={(e) => openFromRow(e, () => drawer.open(item.item_id))}
    >
      <ScoreBadge score={item.score} noise={item.noise} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-1.5">
          <ItemTitle title={item.title} url={item.url} onOpen={() => drawer.open(item.item_id)} className={cn("font-semibold", s >= 4 && "text-sm")} />
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-mute">
          <CompetitorLabel k={item.competitor} className="font-medium text-ink" />
          <CategoryTag category={item.category} />
          <span>{item.publisher}</span>
          <span>{itemDateText(item)}</span>
          {showBadge && item.badge === "late" ? (
            <Tag className="bg-[#fff4e0] font-semibold text-[#8a5a00]" title="Discovered well after its feed date">Found late</Tag>
          ) : null}
          {item.mentions_jfrog ? <MentionsJfrog excerpt={item.excerpt} /> : null}
          {item.flagged ? <Tag className="bg-[#fdeaea] text-[#a32d2d]">Flagged</Tag> : null}
          <ReviewedMark item={item} />
        </div>
        {item.why_it_matters ? <div className="mt-1 text-[#44516a]">{item.why_it_matters}</div> : null}
        {item.excerpt ? (
          <div className="mt-1 line-clamp-2 text-xs text-mute">{item.excerpt}</div>
        ) : (
          <div className="mt-1 text-xs italic text-mute">{NO_TEXT}</div>
        )}
        {extra}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">{actions}</div> : null}
    </div>
  );
}

