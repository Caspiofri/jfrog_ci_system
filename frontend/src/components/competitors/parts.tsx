"use client";
// Pieces shared by the Competitors overview and profile.
import Link from "next/link";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { ExtLink, ScoreBadge, StatusDot, Tag } from "@/components/ci";
import { CATEGORY_COLOR, SOURCE_LABEL, fmtDate, label } from "@/lib/format";
import { competitorName, useMeta } from "@/lib/meta";
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
  if (!total) return <div className="h-2 rounded-sm bg-track" title="No published items this week" />;
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
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-mute">
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
      className="flex flex-col gap-2.5 rounded-md border border-line bg-card px-[18px] py-4 transition-colors hover:border-jgreen">
      <div className="flex items-center justify-between text-[15px] font-semibold">
        <span>{c.name}</span>
        <span className="flex items-center gap-1.5 text-xs font-normal text-mute">
          threat <ScoreBadge score={c.threat} />
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <b className="text-[28px] font-semibold leading-none tabular-nums">{c.items_7d}</b>
        <span className="text-mute">items in 7 days · {c.items_today} in this Brief</span>
      </div>
      <Trend t={c.trend} prev={c.items_prev_7d} />
      <MixBar mix={c.category_mix} />
      <div className="flex flex-wrap gap-1.5 text-xs">
        {c.pending_review ? (
          <Tag className="bg-[#fffaf0] text-[#8a5a00]">{c.pending_review} awaiting review{c.pending_max_score ? ` (max ${c.pending_max_score})` : ""}</Tag>
        ) : null}
        {c.head_to_head_changes ? <Tag className="bg-[#fff7e6] text-[#8a5a00]">{c.head_to_head_changes} head-to-head changes</Tag> : null}
        {c.tracked_changes ? <Tag>{c.tracked_changes} tracked-page changes</Tag> : null}
        {c.mentions_jfrog ? <Tag className="bg-[#eef7f0] text-jgreen-d">{c.mentions_jfrog} mention JFrog</Tag> : null}
      </div>
      {c.top_item ? (
        <div className="border-t border-line pt-2 text-xs">
          <span className="text-mute">Top item: </span>
          <span className="font-medium">{c.top_item.title}</span>
          {c.top_item.score ? <span className="text-mute"> · {c.top_item.score}</span> : null}
        </div>
      ) : (
        <div className="border-t border-line pt-2 text-xs text-mute">No published items this week.</div>
      )}
    </Link>
  );
}

export function DealsTable({ deals, showCompetitor = true }: { deals: Deal[]; showCompetitor?: boolean }) {
  const { data: meta } = useMeta();
  const td = "border-b border-line px-2.5 py-2 align-top";
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {["Date", ...(showCompetitor ? ["Competitor"] : []), "Title", "Source", "Status"].map((h) => (
              <th key={h} className="border-b border-line px-2.5 py-2 text-left text-xs font-semibold text-mute">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {deals.map((d) => (
            <tr key={d.item_id}>
              <td className={`${td} whitespace-nowrap`}>{fmtDate(d.published_at, true)}</td>
              {showCompetitor ? <td className={`${td} whitespace-nowrap`}>{competitorName(meta, d.competitor)}</td> : null}
              <td className={td}><ExtLink href={d.url}>{d.title}</ExtLink></td>
              <td className={`${td} text-mute`}>{d.publisher} · {label(SOURCE_LABEL, d.source)}</td>
              <td className={td}><StatusDot status={d.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
