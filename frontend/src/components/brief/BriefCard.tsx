"use client";
// A published item in the Brief (D44): score with its rubric label, then three labeled rows.
// Every collected string renders as React text (D32); links go through safeHref via ExtLink.
import type { ReactNode } from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { CategoryTag, ExtLink, ScoreBadge, Tag } from "@/components/ci";
import { useItemDrawer } from "@/components/ItemDrawer";
import { AXIS_LABEL, RELATION_LABEL, RUBRIC, itemDateText, textBasisWords } from "@/lib/format";
import { competitorName, useMeta } from "@/lib/meta";
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
    <span className="ml-1 rounded-[3px] border border-dashed border-[#8b5cf6] px-1 text-[10px] font-semibold uppercase tracking-wide text-[#6d28d9]"
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
      <dt className="pt-px text-[11px] font-semibold text-mute">{label}</dt>
      <dd className="m-0 min-w-0">{children}</dd>
    </>
  );
}

/** "Why it matters to JFrog" is the lens only (D42). No lens row and "not related" are different answers. */
function LensView({ item }: { item: Item }) {
  const l = item.lens;
  if (!l) return <span className="text-mute">Not analyzed yet</span>;
  if (l.relation === "not_related" || !l.capability_quote) {
    return <span className="text-mute">No direct link to a JFrog capability</span>;
  }
  const why = l.why_it_matters || l.why;
  return (
    <div className="flex flex-col gap-1">
      <span className="font-medium">{RELATION_LABEL[l.relation] ?? l.relation.replace(/_/g, " ")}</span>
      {why ? <span className="text-[#44516a]">{why}</span> : null}
      <blockquote className="m-0 border-l-2 border-jgreen pl-2 text-xs text-mute">
        <span className="italic">&ldquo;{l.capability_quote}&rdquo;</span>{" "}
        <span className="not-italic">
          —{" "}
          {l.axis ? (
            <Link href={`/capabilities#${encodeURIComponent(l.axis)}`} className="text-jgreen-d hover:underline">
              JFrog capability sheet · {AXIS_LABEL[l.axis] ?? l.axis}
            </Link>
          ) : "JFrog capability sheet"}
        </span>
      </blockquote>
    </div>
  );
}

export function BriefCard({ item, showLate = true, highlight = false }: { item: Item; showLate?: boolean; highlight?: boolean }) {
  const { data: meta } = useMeta();
  const drawer = useItemDrawer();
  const s = item.score ?? 0;
  const basis = textBasisWords(item.text_basis);
  return (
    <article
      className={cn("border-t border-line px-3 py-3 first:border-t-0", EMPHASIS[s], highlight && "bg-[#f3fbf4] ring-2 ring-inset ring-jgreen")}
      data-item={item.item_id}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <ScoreLabel score={item.score} competitor={item.competitor} reason={item.reason} />
        <span className="text-xs font-medium text-ink">· {competitorName(meta, item.competitor)}</span>
        <CategoryTag category={item.category} />
        {showLate && item.badge === "late" ? (
          <Tag className="bg-[#fff4e0] font-semibold text-[#8a5a00]" title="Discovered well after it was published">Found late</Tag>
        ) : null}
        {item.mentions_jfrog ? <Tag className="bg-[#eef7f0] font-semibold text-jgreen-d">Mentions JFrog</Tag> : null}
        {item.flagged ? <Tag className="bg-[#fdeaea] text-[#a32d2d]">Flagged</Tag> : null}
      </div>
      <div className="mt-1.5 flex items-start gap-1.5">
        <button type="button" onClick={() => drawer.open(item.item_id)} className={cn("text-left font-semibold hover:text-jgreen-d", s >= 4 && "text-sm")}>
          {item.title}
        </button>
        <ExtLink href={item.url} className="mt-0.5 shrink-0 text-mute">
          <ExternalLink className="size-3.5" aria-label="Open the source" />
        </ExtLink>
      </div>
      <dl className="m-0 mt-2 grid grid-cols-1 gap-x-3 gap-y-1.5 sm:grid-cols-[10.5rem_minmax(0,1fr)]">
        <Row label="What happened">
          {item.excerpt.trim() ? <span className="text-[#44516a]">{item.excerpt}</span> : <span className="text-mute">Only the headline is available.</span>}
        </Row>
        <Row label="Why it matters to JFrog"><LensView item={item} /></Row>
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
