"use client";
// A published item in the Brief (D44): score with its rubric label, then three labeled rows.
// Every collected string renders as React text (D32); links go through safeHref via ExtLink.
import { MentionsJfrog } from "@/components/MentionsJfrog";
import { CompetitorLabel } from "@/components/CompetitorAvatar";
import type { ReactNode } from "react";
import { CategoryTag, ItemTitle, ScoreBadge, Tag, openFromRow } from "@/components/ci";
import { ReviewedMark } from "@/components/ReviewedMark";
import { useItemDrawer } from "@/components/ItemDrawer";
import { LensView } from "@/components/LensView";
import { RUBRIC, itemDateText, textBasisWords } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import type { Item, Meta } from "@/lib/types";
import { cn } from "@/lib/utils";

const EMPHASIS: Record<number, string> = {
  5: "bg-[#fff1f0] border-l-4 border-l-[#9b1c1c]",
  4: "bg-[#fff7f6] border-l-4 border-l-[#e5483b]",
  3: "border-l-4 border-l-[#f59e0b]",
};

/** Dev mock scenarios only (src/lib/mock.ts). */
export function MockTag({ what }: { what?: string }) {
  return (
    <span className="ml-1 rounded-[3px] border border-dashed border-[#8b5cf6] px-1 text-[0.625rem] font-semibold uppercase tracking-wide text-[#6d28d9]"
      title={`Dev mock: ${what ?? "this value"} isn't served by the API yet`}>
      mock
    </span>
  );
}

function rubricFor(meta: Meta | undefined, score: number | null, competitor: string) {
  if (!score) return null;
  const served = meta?.rubric?.find((r) => r.score === score);
  const line = served ?? RUBRIC[score];
  if (!line) return null;
  return { label: line.label, rule: competitor === "industry" ? line.industry : line.competitor };
}

/** Score badge plus its rubric v2 label. Tooltip: the rubric line (industry column for industry items), then the
 * ranker's reason for this item: interpretation lives here, not in the card's "What happened". */
export function ScoreLabel({ score, competitor, reason }: { score: number | null; competitor: string; reason?: string }) {
  const { data: meta } = useMeta();
  const r = rubricFor(meta, score, competitor);
  const tip = [r ? `${score} · ${r.label}: ${r.rule}` : null, reason ? `Why this score: ${reason}` : null].filter(Boolean).join("\n\n") || undefined;
  return (
    <span className="inline-flex items-center gap-1.5" title={tip}>
      <ScoreBadge score={score} title={tip} />
      {r ? <span className="text-xs font-semibold text-ink">{r.label}</span> : null}
    </span>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="pt-px text-[0.6875rem] font-semibold text-mute">{label}</dt>
      <dd className="m-0 min-w-0">{children}</dd>
    </>
  );
}

export function BriefCard({ item, showLate = true, highlight = false }: { item: Item; showLate?: boolean; highlight?: boolean }) {
  const drawer = useItemDrawer();
  const s = item.score ?? 0;
  const basis = textBasisWords(item.text_basis);
  return (
    <article
      className={cn("cursor-pointer border-t border-line px-3 py-3 first:border-t-0 hover:bg-page/60", EMPHASIS[s], highlight && "bg-[#f3fbf4] ring-2 ring-inset ring-jgreen")}
      data-item={item.item_id}
      onClick={(e) => openFromRow(e, () => drawer.open(item.item_id))}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <ScoreLabel score={item.score} competitor={item.competitor} reason={item.reason} />
        <span className="text-xs font-medium text-ink">·</span><CompetitorLabel k={item.competitor} className="text-xs font-medium text-ink" />
        <CategoryTag category={item.category} />
        {showLate && item.badge === "late" ? (
          <Tag className="bg-[#fff4e0] font-semibold text-[#8a5a00]" title="Discovered well after its feed date">Found late</Tag>
        ) : null}
        {item.mentions_jfrog ? <MentionsJfrog excerpt={item.excerpt} mention={item.jfrog_mention} /> : null}
        {item.flagged ? <Tag className="bg-[#fdeaea] text-[#a32d2d]">Flagged</Tag> : null}
        <ReviewedMark item={item} />
      </div>
      <div className="mt-1.5 flex items-start gap-1.5">
        <ItemTitle title={item.title} url={item.url} onOpen={() => drawer.open(item.item_id)} className={cn("font-semibold", s >= 4 && "text-sm")} />
      </div>
      <dl className="m-0 mt-2 grid grid-cols-1 gap-x-3 gap-y-1.5 sm:grid-cols-[10.5rem_minmax(0,1fr)]">
        <Row label="What happened">
          {item.excerpt.trim() ? <span className="text-[#44516a]">{item.excerpt}</span> : <span className="text-mute">Only the headline is available.</span>}
        </Row>
        <Row label="Why it matters to JFrog"><LensView lens={item.lens} status={item.lens_status} /></Row>
        <Row label="Evidence">
          <span className="text-xs text-mute">
            {item.publisher} · {itemDateText(item)} ·{" "}
            {basis ?? "Text basis not reported"}
          </span>
        </Row>
      </dl>
    </article>
  );
}
