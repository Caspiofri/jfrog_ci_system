"use client";
// Pieces shared by the Competitors overview and profile.
import { CompetitorAvatar, CompetitorLabel } from "@/components/CompetitorAvatar";
import Link from "next/link";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { Hint, ItemTitle, ScoreBadge, StatusDot, Tag } from "@/components/ci";

export const TOP_SCORE_LABEL = "Top score this week";
import { useItemDrawer } from "@/components/ItemDrawer";
import { CardSparkline } from "@/components/competitors/Sparkline";
import { CATEGORY_COLOR, SOURCE_LABEL, fmtDate, label } from "@/lib/format";
import type { CompetitorCard, Deal } from "@/lib/types";

export function Trend({ t, prev }: { t: CompetitorCard["trend"]; prev: number }) {
  const Icon = t.direction === "up" ? ArrowUpRight : t.direction === "down" ? ArrowDownRight : ArrowRight;
  return (
    <span className="inline-flex items-center gap-0.5 text-xs text-mute" title={`Previous 7 days: ${prev}`}>
      <Icon className="size-3.5" />
      {t.delta > 0 ? "+" : ""}{t.delta} vs previous 7 days
    </span>
  );
}

/** The category mix bar (prototype .mix), with a legend under it so color is never the only cue. */
export function MixBar({ mix, legend = false }: { mix: CompetitorCard["category_mix"]; legend?: boolean }) {
  const total = mix.reduce((a, b) => a + b.count, 0);
  if (!total) return <div className="h-2 rounded-sm bg-track" title="No cleared items this week" />;
  return (
    <div>
      <div className="flex h-2 gap-px overflow-hidden rounded-sm bg-track" role="img"
        aria-label={mix.map((m) => `${m.category} ${m.count}`).join(", ")}>
        {mix.map((m) => (
          <i key={m.category} className="block h-full" title={`${m.category}: ${m.count}`}
            style={{ width: `${(100 * m.count) / total}%`, background: CATEGORY_COLOR[m.category] ?? "#9aa5b5" }} />
        ))}
      </div>
      {legend ? (
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[0.6875rem] text-mute">
          {mix.map((m) => (
            <span key={m.category} className="inline-flex items-center gap-1">
              <i className="inline-block size-2 rounded-sm" style={{ background: CATEGORY_COLOR[m.category] ?? "#9aa5b5" }} />
              {m.category} {m.count}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function CompetitorCardView({ c }: { c: CompetitorCard }) {
  return (
    <Link href={`/competitors/${encodeURIComponent(c.key)}`}
      className="flex flex-col gap-2.5 rounded-md border border-line bg-card px-[1.125rem] py-4 transition-colors hover:border-jgreen">
      <div className="flex items-center justify-between text-[0.9375rem] font-semibold">
        <span className="inline-flex items-center gap-2"><CompetitorAvatar k={c.key} name={c.name} size="md" />{c.name}</span>
        {/* the label lives in the hover and on keyboard focus (Hint is focusable); screen readers read it as text */}
        <Hint text={TOP_SCORE_LABEL} className="inline-flex items-center text-xs font-normal">
          <span className="sr-only">{TOP_SCORE_LABEL}: </span>
          <span data-top-score><ScoreBadge score={c.threat} /></span>
        </Hint>
      </div>
      {/* D112: what is waiting, then what happened; the heatmap above carries the counts */}
      {c.pending_review || c.mentions_jfrog ? (
        <div className="flex flex-wrap gap-1.5 text-xs" data-card-tags>
          {c.pending_review ? (
            <Tag className="bg-[#fffaf0] text-[#8a5a00]">{c.pending_review} awaiting review{c.pending_max_score ? ` (max ${c.pending_max_score})` : ""}</Tag>
          ) : null}
          {c.mentions_jfrog ? <Tag className="bg-[#eef7f0] text-jgreen-d">{c.mentions_jfrog} mention JFrog</Tag> : null}
        </div>
      ) : null}
      <CardSparkline k={c.key} />
      {/* one top item: GET /competitors sends only top_item, so up to 3 would need an API change (D112) */}
      {c.top_item ? (
        <div className="border-t border-line pt-2 text-xs" data-top-item>
          <span className="text-mute">Top item: </span>
          <span className="font-medium">{c.top_item.title}</span>
          {c.top_item.score ? <span className="text-mute"> · {c.top_item.score}</span> : null}
          {c.top_item.published_at ? <span className="text-mute"> · {fmtDate(c.top_item.published_at)}</span> : null}
        </div>
      ) : (
        <div className="border-t border-line pt-2 text-xs text-mute">No cleared items this week.</div>
      )}
    </Link>
  );
}

export function DealsTable({ deals, showCompetitor = true }: { deals: Deal[]; showCompetitor?: boolean }) {
  const drawer = useItemDrawer();
  const td = "border-b border-line px-2.5 py-2 align-top";
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {["Article date", ...(showCompetitor ? ["Competitor"] : []), "Title", "Source", "Status"].map((h) => (
              <th key={h} className="border-b border-line px-2.5 py-2 text-left text-xs font-semibold text-mute">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {deals.map((d) => (
            <tr key={d.item_id}>
              <td className={`${td} whitespace-nowrap`}>{fmtDate(d.published_at, true)}</td>
              {showCompetitor ? <td className={`${td} whitespace-nowrap`}><CompetitorLabel k={d.competitor} /></td> : null}
              <td className={td}><ItemTitle title={d.title} url={d.url} publisher={d.publisher} onOpen={() => drawer.open(d.item_id)} /></td>
              <td className={`${td} text-mute`}>{d.publisher} · {label(SOURCE_LABEL, d.source)}</td>
              <td className={td}><StatusDot status={d.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
