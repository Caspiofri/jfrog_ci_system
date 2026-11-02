"use client";
import { CompetitorAvatar } from "@/components/CompetitorAvatar";
import { Suspense } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Async, Empty, HBars, KpiTile, Loading, Panel, ScoreBadge } from "@/components/ci";
import { ItemRow } from "@/components/ItemRow";
import { ActivityChart } from "@/components/competitors/ActivityChart";
import { HeadToHead } from "@/components/competitors/HeadToHead";
import { DealsTable, MixBar, Trend } from "@/components/competitors/parts";
import { path, useRecord } from "@/lib/api";
import { CATEGORY_COLOR, fmtDate } from "@/lib/format";
import { useUrlState } from "@/lib/useParams";
import type { CompetitorProfile } from "@/lib/types";

const PAGE = 10;

export default function ProfilePage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <Profile />
    </Suspense>
  );
}

function Profile() {
  const { key } = useParams<{ key: string }>();
  const { get, set } = useUrlState();
  const offset = Number(get("offset") || 0);
  const q = useRecord<CompetitorProfile>(path(`/competitors/${encodeURIComponent(key)}`, { limit: PAGE, offset }), key, (d) => d.key);
  return (
    <>
      <div>
        <Button asChild variant="outline" size="sm" className="h-7 text-xs">
          <Link href="/competitors"><ChevronLeft className="size-3.5" /> All competitors</Link>
        </Button>
      </div>
      <Async {...q} retry={() => q.mutate()} rows={8}>
        {(p) => {
          const c = p.card;
          return (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h1 className="m-0 flex items-center gap-2 text-[22px] font-semibold"><CompetitorAvatar k={p.key} name={p.name} size="lg" />{p.name}</h1>
                  <div className="mt-0.5 text-mute">
                    Week to {fmtDate(p.date, true)} · last activity {fmtDate(c.last_activity_at, true)}
                  </div>
                </div>
                <span className="flex items-center gap-2 text-mute">Top score this week <ScoreBadge score={c.threat} /></span>
              </div>

              <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
                <KpiTile value={c.items_7d} label="Published in 7 days" sub={<Trend t={c.trend} prev={c.items_prev_7d} />} />
                <KpiTile value={c.items_today} label="In this Brief" />
                <KpiTile value={c.pending_review} label="Awaiting review" sub={c.pending_max_score ? <span className="text-mute">highest score {c.pending_max_score}</span> : undefined} />
                <KpiTile value={c.head_to_head_changes ?? "—"} label="Head-to-head changes" sub={<span className="text-mute">{c.tracked_changes ?? 0} tracked-page changes</span>} />
              </div>

              <Panel title="What happened this week?">
                {p.summary.status === "ok" && p.summary.text ? <p className="m-0">{p.summary.text}</p> : (
                  <Empty>The AI &ldquo;this week&rdquo; summary isn&apos;t built yet. The latest items below are the evidence.</Empty>
                )}
              </Panel>

              <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]">
                <Panel title="How active are they?" cap={`Published items per day by feed date, ${p.activity.days} days · ${p.activity.total} published in total`}>
                  {p.activity.series.some((r) => r.items) ? <ActivityChart series={p.activity.series} /> : <Empty>No published items in the last {p.activity.days} days.</Empty>}
                </Panel>
                <Panel title="What are they focused on?" cap="Published items this week">
                  {c.category_mix.length ? (
                    <>
                      <MixBar mix={c.category_mix} legend />
                      <div className="mt-3">
                        <HBars rows={c.category_mix.map((m) => ({ label: m.category, value: m.count, color: CATEGORY_COLOR[m.category] }))} />
                      </div>
                    </>
                  ) : <Empty>No published items this week.</Empty>}
                </Panel>
              </div>

              {p.head_to_head ? (
                <div id="head-to-head" className="scroll-mt-20">
                <Panel title="How do they compare with JFrog?" info="Changed cells are highlighted and go to review. Not stated means the page says nothing on that axis, not that there is a gap.">
                  <HeadToHead competitor={p.key} name={p.name} axes={p.head_to_head.axes} />
                </Panel>
                </div>
              ) : (
                <Panel title="How do they compare with JFrog?"><Empty>{p.name} is a channel, not a vendor: no head-to-head.</Empty></Panel>
              )}

              <Panel title="What did they do lately?" cap={`Newest feed date first · ${p.latest_items.total} published items`}>
                {p.latest_items.items.length ? p.latest_items.items.map((it) => <ItemRow key={it.item_id} item={it} showBadge={false} />) : <Empty>No published items.</Empty>}
                {p.latest_items.total > PAGE ? (
                  <div className="mt-2.5 flex items-center justify-end gap-2">
                    <span className="text-xs text-mute">{offset + 1}–{Math.min(offset + PAGE, p.latest_items.total)} of {p.latest_items.total}</span>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset === 0} onClick={() => set({ offset: String(Math.max(0, offset - PAGE)) })}>Previous</Button>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset + PAGE >= p.latest_items.total} onClick={() => set({ offset: String(offset + PAGE) })}>Next</Button>
                  </div>
                ) : null}
              </Panel>

              {p.deals.length ? (
                <Panel title="Who are they buying or partnering with?" cap="Funding/M&A/Partnerships items as collected">
                  <DealsTable deals={p.deals} showCompetitor={false} />
                </Panel>
              ) : null}
            </>
          );
        }}
      </Async>
    </>
  );
}
