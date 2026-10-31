"use client";
import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Async, Empty, ErrorNote, KpiTile, Loading, PageHead, Panel, Tag } from "@/components/ci";
import { FilterSelect } from "@/components/FilterSelect";
import { useItemDrawer } from "@/components/ItemDrawer";
import { ItemRow } from "@/components/ItemRow";
import { IntensityChart } from "@/components/brief/IntensityChart";
import { ApiError, path, send, useApi } from "@/lib/api";
import { PATTERN_LABEL, SCORE_COLOR, delta, fmtDate, fmtDateTime, fmtLongDate, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import { useUrlState } from "@/lib/useParams";
import type { Brief, BriefInsights, BriefRow, Insight, Page } from "@/lib/types";

const TOP = 5;
const PAGE = 50;

const KPI_LABEL: Record<string, string> = {
  items: "Items in this Brief",
  important: "Rated 4 or 5",
  found_late: "Found late",
  mentions_jfrog: "Mention JFrog",
};

/** Backfill comes from the API (BACKEND_REQUESTS.md #1), never from the date. */
function isBackfill(b: Brief | undefined, row: BriefRow | undefined): boolean {
  const w = b?.window;
  return Boolean(w?.backfill || w?.anchor_kind === "import" || row?.backfill || row?.anchor_kind === "import");
}

export default function BriefPage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <BriefScreen />
    </Suspense>
  );
}

function BriefScreen() {
  const { get, set } = useUrlState();
  const { data: meta } = useMeta();
  const briefs = useApi<Page<BriefRow>>(path("/briefs", { limit: 200 }));
  const dates = briefs.data?.items.map((r) => r.date) ?? []; // newest first
  const date = get("date") || briefs.data?.items[0]?.date || "";
  const competitor = get("competitor");
  const category = get("category");
  const all = get("all") === "1";
  const offset = Number(get("offset") || 0);
  const [hl, setHl] = useState<string | null>(null);

  const brief = useApi<Brief>(
    briefs.data ? path("/brief", { date: date || undefined, competitor, category, limit: all ? PAGE : TOP, offset: all ? offset : 0 }) : null,
  );
  const row = briefs.data?.items.find((r) => r.date === date);
  const backfill = isBackfill(brief.data, row);
  const i = dates.indexOf(date);
  const older = i >= 0 && i < dates.length - 1 ? dates[i + 1] : null;
  const newer = i > 0 ? dates[i - 1] : null;
  const go = (d: string | null) => d && set({ date: d, offset: null });

  const highlighted = useMemo(() => {
    const ins = brief.data?.insights.items.find((x) => x.insight_id === hl);
    return new Set(ins?.item_ids ?? []);
  }, [brief.data, hl]);

  return (
    <>
      <PageHead
        title="Daily Brief"
        sub={
          <span className="mt-1 flex items-center gap-2">
            <Button variant="outline" size="icon" className="size-7" disabled={!older} onClick={() => go(older)} aria-label="Previous Brief">
              <ChevronLeft className="size-4" />
            </Button>
            <span className="min-w-[13rem] text-center">{date ? fmtLongDate(date) : briefs.isLoading ? "Loading…" : "No Brief yet"}</span>
            <Button variant="outline" size="icon" className="size-7" disabled={!newer} onClick={() => go(newer)} aria-label="Next Brief">
              <ChevronRight className="size-4" />
            </Button>
            {backfill ? <Tag className="bg-[#e8eefb] font-semibold text-[#3f5b8f]">Initial import (backfill)</Tag> : null}
          </span>
        }
        tools={
          <>
            <FilterSelect ariaLabel="Competitor" allLabel="All competitors" value={competitor} onChange={(v) => set({ competitor: v, offset: null })}
              options={(meta?.competitors ?? []).map((c) => ({ value: c.key, label: c.name }))} />
            <FilterSelect ariaLabel="Category" allLabel="All categories" value={category} onChange={(v) => set({ category: v, offset: null })}
              options={(meta?.categories ?? []).map((c) => ({ value: c, label: c }))} />
          </>
        }
      />

      {briefs.error ? <ErrorNote error={briefs.error} onRetry={() => briefs.mutate()} /> : null}
      {briefs.data && !briefs.data.items.length ? (
        <Panel><Empty>No Brief yet: the store has no successful daily run.</Empty></Panel>
      ) : null}

      {briefs.data?.items.length ? (
        <Async {...brief} retry={() => brief.mutate()} rows={8}>
          {(b) =>
            b.status === "missing" || !b.window || !b.counts ? (
              <Panel><Empty>No Brief for {fmtLongDate(b.date)}: there was no successful daily run that day.</Empty></Panel>
            ) : (
              <>
                <div className="-mt-2 text-xs text-mute">
                  {backfill
                    ? "The 14-day import that started the store. Everything in it was published before the first run, so \"Found late\" badges are hidden here."
                    : `Everything discovered from ${fmtDateTime(b.window.prev_anchor)} to ${fmtDateTime(b.window.anchor)} Israel time (${b.window.hours} h).`}
                </div>

                <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
                  {b.kpis.map((k) => {
                    if (k.key === "found_late" && backfill) return <KpiTile key={k.key} value="—" label={KPI_LABEL[k.key]} sub={<span className="text-mute">not shown for the backfill</span>} />;
                    const d = delta(k.value, k.prev);
                    return <KpiTile key={k.key} value={k.value} label={KPI_LABEL[k.key] ?? k.key} sub={<span className={d.cls}>{d.text}</span>} />;
                  })}
                </div>

                <InsightsPanel date={b.date} insights={b.insights} hl={hl} setHl={setHl} onRefreshed={() => brief.mutate()} />

                <Panel
                  title="What was published in this Brief?"
                  cap={`Sorted by importance · ${b.items.total} items${competitor || category ? " match the filters" : ""}`}
                >
                  {b.counts.awaiting_review ? (
                    <div className="mb-2 text-xs text-mute">
                      {b.counts.awaiting_review} more items from this window are waiting for review at the current level ({b.level ?? meta?.level}).{" "}
                      <Link href="/review" className="text-jgreen-d hover:underline">Open the review queue</Link>
                    </div>
                  ) : null}
                  {b.items.items.length ? (
                    b.items.items.map((it) => <ItemRow key={it.item_id} item={it} showBadge={!backfill} highlight={highlighted.has(it.item_id)} />)
                  ) : (
                    <Empty>{competitor || category ? "Nothing matches these filters." : "Nothing was published in this window."}</Empty>
                  )}
                  <FeedFooter total={b.items.total} all={all} offset={offset} set={set} />
                </Panel>

                {b.intensity ? (
                  <Panel title="Is this day unusual?" cap={`Sum of importance of published items per discovery day, ${b.intensity.days} days`}>
                    <IntensityChart series={b.intensity.series} current={b.date} />
                  </Panel>
                ) : null}
              </>
            )
          }
        </Async>
      ) : null}
    </>
  );
}

function FeedFooter({ total, all, offset, set }: { total: number; all: boolean; offset: number; set: (p: Record<string, string | null>) => void }) {
  if (!all) {
    return total > TOP ? (
      <div className="mt-2.5">
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => set({ all: "1", offset: null })}>Show all {total} items</Button>
      </div>
    ) : null;
  }
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => set({ all: null, offset: null })}>Show top items only</Button>
      {total > PAGE ? (
        <>
          <span className="flex-1" />
          <span className="text-xs text-mute">{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
          <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset === 0} onClick={() => set({ offset: String(Math.max(0, offset - PAGE)) })}>Previous</Button>
          <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset + PAGE >= total} onClick={() => set({ offset: String(offset + PAGE) })}>Next</Button>
        </>
      ) : null}
    </div>
  );
}

const INSIGHT_STATUS: Record<string, string> = {
  not_generated: "No insights have been generated for this Brief yet.",
  none: "No pattern this time: no group of at least two related stories in the window.",
  failed: "Generating insights failed for this Brief.",
  missing: "No insights: there is no Brief for this date.",
};

function InsightsPanel({ date, insights, hl, setHl, onRefreshed }: {
  date: string; insights: BriefInsights; hl: string | null; setHl: (id: string | null) => void; onRefreshed: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const enabled = insights.enabled !== false;
  const refresh = async () => {
    setBusy(true);
    setErr(null);
    try {
      await send("POST", `/api/v1/brief/${encodeURIComponent(date)}/insights/refresh`);
      onRefreshed();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const rejected = Array.isArray(insights.rejected) ? insights.rejected.length : insights.rejected;
  const cap = insights.generated_at
    ? `Generated ${fmtDateTime(insights.generated_at)}${insights.trigger === "refresh" ? " (refreshed)" : ""}${insights.window?.from ? ` · window ${fmtDate(insights.window.from)}–${fmtDate(insights.window.to)}` : ""}${rejected ? ` · ${rejected} rejected by the quote check` : ""}`
    : "Select one to highlight the items it rests on";
  return (
    <Panel
      title="What patterns matter today?"
      cap={cap}
      right={
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={refresh} disabled={busy || !enabled}
          title={enabled ? "Regenerate after analyst approvals; the 06:00 version is kept" : "Insights are off until the expected-insights file is saved (D37)"}>
          <RefreshCw className={busy ? "size-3 animate-spin" : "size-3"} /> Refresh insights
        </Button>
      }
    >
      {err ? <div className="mb-2"><ErrorNote error={err} /></div> : null}
      {!enabled && !insights.items.length ? (
        <Empty>Insights are turned off until the expected-insights file is saved (D37), so none are shown for this Brief.</Empty>
      ) : insights.items.length ? (
        <>
          {insights.status === "partial" ? <div className="mb-2 text-xs text-mute">Fewer than 3 insights passed the checks this time.</div> : null}
          <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))]">
            {insights.items.map((x) => (
              <InsightCard key={x.insight_id} ins={x} selected={hl === x.insight_id} onSelect={() => setHl(hl === x.insight_id ? null : x.insight_id)} />
            ))}
          </div>
        </>
      ) : (
        <Empty>{INSIGHT_STATUS[insights.status] ?? `No insights (${insights.status}).`}</Empty>
      )}
    </Panel>
  );
}

function InsightCard({ ins, selected, onSelect }: { ins: Insight; selected: boolean; onSelect: () => void }) {
  const drawer = useItemDrawer();
  const top = SCORE_COLOR[ins.max_score ?? 0]?.[0] ?? "#e3e8ef";
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onSelect}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect())}
      className={`flex cursor-pointer flex-col gap-2 rounded-md border bg-card px-4 py-3 transition-colors hover:border-jgreen ${selected ? "border-jgreen ring-1 ring-jgreen" : "border-line"}`}
      style={{ borderTop: `4px solid ${top}` }}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Tag>{label(PATTERN_LABEL, ins.pattern)}</Tag>
        {ins.max_score ? <span className="text-xs text-mute">top importance {ins.max_score}</span> : null}
        <span className="text-xs text-mute">· {ins.item_ids.length} items, {ins.story_ids.length} stories</span>
      </div>
      <h3 className="m-0 text-sm font-semibold">{ins.title}</h3>
      <p className="m-0 text-[#44516a]">{ins.summary}</p>
      {ins.why_it_matters ? <p className="m-0 text-xs text-mute"><b className="font-semibold text-ink">Why it matters: </b>{ins.why_it_matters}</p> : null}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {ins.claims.map((c, k) => (
          <li key={k} className="text-xs">
            <div>{c.text}</div>
            {c.quote ? <blockquote className="my-1 border-l-2 border-line pl-2 italic text-mute">&ldquo;{c.quote}&rdquo;</blockquote> : null}
            <div className="flex flex-wrap gap-1">
              {c.item_ids.map((id) => (
                <button key={id} type="button" onClick={(e) => { e.stopPropagation(); drawer.open(id); }}
                  className="rounded-[3px] border border-line px-1.5 text-[11px] text-mute hover:border-jgreen hover:text-jgreen-d" title="Open the cited item">
                  {id.slice(0, 6)}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {ins.baseline_note ? <div className="text-[11px] text-mute">{ins.baseline_note}</div> : null}
    </div>
  );
}
