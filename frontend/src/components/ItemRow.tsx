"use client";
// One item in a list (prototype .row with r5/r4/r3 emphasis). Title opens the drawer; the icon opens the source.
import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { CategoryTag, ExtLink, ScoreBadge, Tag } from "@/components/ci";
import { useItemDrawer } from "@/components/ItemDrawer";
import { NO_TEXT, itemDateText } from "@/lib/format";
import { competitorName, useMeta } from "@/lib/meta";
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
  const { data: meta } = useMeta();
  const drawer = useItemDrawer();
  const s = item.noise ? 0 : (item.score ?? 0);
  return (
    <div
      className={cn(
        "flex items-start gap-3 border-t border-line py-2.5 first:border-t-0",
        EMPHASIS[s],
        s > 0 && s <= 2 && "opacity-80",
        highlight && "ring-2 ring-jgreen ring-inset bg-[#f3fbf4]",
      )}
      data-item={item.item_id}
    >
      <ScoreBadge score={item.score} noise={item.noise} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-1.5">
          <button type="button" onClick={() => drawer.open(item.item_id)} className={cn("text-left font-semibold hover:text-jgreen-d", s >= 4 && "text-sm")}>
            {item.title}
          </button>
          <ExtLink href={item.url} className="mt-0.5 shrink-0 text-mute">
            <ExternalLink className="size-3.5" aria-label="Open the source" />
          </ExtLink>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-mute">
          <span className="font-medium text-ink">{competitorName(meta, item.competitor)}</span>
          <CategoryTag category={item.category} />
          <span>{item.publisher}</span>
          <span>{itemDateText(item)}</span>
          {showBadge && item.badge === "late" ? (
            <Tag className="bg-[#fff4e0] font-semibold text-[#8a5a00]" title="Discovered well after publication">Found late</Tag>
          ) : null}
          {item.mentions_jfrog ? <Tag className="bg-[#eef7f0] font-semibold text-jgreen-d">Mentions JFrog</Tag> : null}
          {item.flagged ? <Tag className="bg-[#fdeaea] text-[#a32d2d]">Flagged</Tag> : null}
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
