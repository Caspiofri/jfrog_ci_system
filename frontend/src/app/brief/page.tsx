"use client";
import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight, ExternalLink, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Async, Empty, ErrorNote, ExtLink, Loading, PageHead, Panel, ScoreBadge, Tag } from "@/components/ci";
import { FilterSelect } from "@/components/FilterSelect";
import { useItemDrawer } from "@/components/ItemDrawer";
import { BriefCard, MockTag } from "@/components/brief/BriefCard";
import { ApiError, path, send, useApi } from "@/lib/api";
import { LEVEL_LABEL, PATTERN_LABEL, SCORE_COLOR, fmtDate, fmtDateTime, fmtLongDate, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import { MOCK, mockBrief, useMock } from "@/lib/mock";
import { useUrlState } from "@/lib/useParams";
import type { Brief, BriefInsights, BriefRow, BriefSummary, CitedItemRow, Claim, Insight, ItemDetail, Page } from "@/lib/types";

const TOP = 5;
const PAGE = 50;

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

  const raw = useApi<Brief>(
    briefs.data ? path("/brief", { date: date || undefined, competitor, category, limit: all ? PAGE : TOP, offset: all ? offset : 0 }) : null,
  );
  const mock = useMock();
  const scenario = MOCK && mock ? get("mock") : "";
  const insightsScenario = MOCK && mock ? get("mock_insights") : "";
  const data = useMemo(
    () => (raw.data ? mockBrief(mock, raw.data, scenario, insightsScenario) : undefined),
    [mock, raw.data, scenario, insightsScenario],
  );
  const brief = { ...raw, data };
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

      {MOCK && mock ? (
        <div className="rounded border border-dashed border-[#8b5cf6] bg-[#f5f3ff] px-3 py-2 text-xs text-[#5b21b6]">
          Dev mock mode: values marked <MockTag /> are invented for a state check, not data.
          {scenario || insightsScenario ? <> Scenario: <b>{[scenario, insightsScenario].filter(Boolean).join(", ")}</b>.</> : <> No scenario set, so everything below is the real API.</>}
        </div>
      ) : null}
      {briefs.error ? <ErrorNote error={briefs.error} onRetry={() => briefs.mutate()} /> : null}
      {briefs.data && !briefs.data.items.length ? (
        <Panel><Empty>No Brief yet: the store has no successful daily run.</Empty></Panel>
      ) : null}

      {briefs.data?.items.length ? (
        <Async {...brief} retry={() => brief.mutate()} rows={8}>
          {(b) =>
            b.status === "missing" || !b.window || !b.summary ? (
              <Panel><Empty>No Brief for {fmtLongDate(b.date)}: there was no successful daily run that day.</Empty></Panel>
            ) : (
              <>
                <div className="-mt-2 text-xs text-mute">
                  {backfill
                    ? "The 14-day import that started the store. Everything in it was published before the first run, so \"Found late\" badges are hidden here."
                    : `Everything discovered from ${fmtDateTime(b.window.prev_anchor)} to ${fmtDateTime(b.window.anchor)} Israel time (${b.window.hours} h).`}
                </div>

                <SummaryBlock date={b.date} s={b.summary} />

                <Panel
                  title="What was published in this Brief?"
                  cap={`Sorted by importance · ${b.items.total} ${b.items.total === 1 ? "item" : "items"}${competitor || category ? " match the filters" : ""}`}
                >
                  {b.items.items.length ? (
                    b.items.items.map((it) => <BriefCard key={it.item_id} item={it} showLate={!backfill} highlight={highlighted.has(it.item_id)} />)
                  ) : (
                    <Empty>
                      {competitor || category
                        ? "Nothing matches these filters."
                        : b.summary.held
                          ? "Nothing was published in this window. The held items above aren't verified yet, so they aren't part of the Brief."
                          : "Nothing was published in this window."}
                    </Empty>
                  )}
                  <FeedFooter total={b.items.total} all={all} offset={offset} set={set} />
                </Panel>

                <InsightsPanel date={b.date} insights={b.insights} hl={hl} setHl={setHl} onRefreshed={() => brief.mutate()} />
              </>
            )
          }
        </Async>
      ) : null}
    </>
  );
}

function SummaryBlock({ date, s }: { date: string; s: BriefSummary }) {
  const mock = s.mock ? <MockTag what="this count" /> : null;
  const level = label(LEVEL_LABEL, s.level);
  const unscored = s.held_by_preliminary_score?.unscored ?? 0;
  return (
    <section className="rounded-md border border-line bg-card px-[18px] py-4" aria-label="Brief summary">
      <div className="flex flex-wrap items-baseline gap-x-2 text-[15px]">
        <span><b className="text-xl font-semibold tabular-nums">{s.published}</b> in Brief</span>
        <span className="text-mute">(<b className="font-semibold tabular-nums text-ink">{s.published_high}</b> rated 4–5)</span>
        <span className="text-mute">·</span>
        <Link href="/competitors" className="hover:underline"
          title={`Published but scored below ${s.brief_min_score}: score 2 is on the competitor profile, score 1 on its timeline`}>
          <b className="font-semibold tabular-nums">{s.published_below}</b> lower-scored on competitor pages
        </Link>
        {mock}
      </div>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 text-[15px]">
        <span><b className="text-xl font-semibold tabular-nums text-[#8a5a00]">{s.held}</b> held for review at {level}</span>
        <span className="text-mute">·</span>
        <span><b className="font-semibold tabular-nums">{s.held_high}</b> preliminarily rated 4–5</span>
        {unscored ? (
          <span className="text-[#a32d2d]" title="The ranker gave these no score (a model failure), so they aren't counted as low">
            · <b className="font-semibold tabular-nums">{unscored}</b> not scored
          </span>
        ) : null}
        {mock}
        {s.held ? (
          <Link href={`/review?brief=${encodeURIComponent(date)}`} className="inline-flex items-center gap-1 font-semibold text-jgreen-d hover:underline">
            <ArrowRight className="size-3.5" aria-hidden /> Review these
          </Link>
        ) : null}
      </div>
      <div className="mt-2 text-xs text-mute">
        {s.held
          ? `At ${level}, some items wait for an analyst before they reach the Brief, for example ${s.level === "strict" ? "items from a source that isn't vetted, or " : ""}items about pricing or M&A, or that mention JFrog. Until then they are not verified and not part of it.`
          : "Nothing from this window is waiting for review."}
      </div>
    </section>
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

/** Contract §10.4: `status` is the state to show. null = show the insights. */
function insightState(ins: BriefInsights): string | null {
  switch (ins.status) {
    case "ok":
      return ins.items.length ? null : "No cross-competitor pattern met the evidence bar today.";
    case "disabled":
      return "Pattern analysis is not enabled for this Brief.";
    case "refreshing":
      return "refreshing";
    case "failed":
      return "failed";
    case "none_passed":
      return `No cross-competitor pattern met the evidence bar today (${ins.rejected ?? 0} candidates rejected).`;
    case "not_run":
      return "Pattern analysis didn't run for this Brief.";
    case "missing":
      return "There is no Brief for this date.";
    default:
      return ins.items.length ? null : `No patterns for this Brief (${ins.status.replace(/_/g, " ")}).`;
  }
}

/** The analyst's manual check of the insights (1 Nov). Insights stay experimental until summaries stop overstating. */
const INSIGHTS_CHECK =
  "Checked on 1 Nov (n = 4 insights, 12 claims): 11 of 12 claims supported, 12 of 12 citations correct; summaries overstated in all 4.";

function InsightsPanel({ date, insights, hl, setHl, onRefreshed }: {
  date: string; insights: BriefInsights; hl: string | null; setHl: (id: string | null) => void; onRefreshed: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const enabled = insights.status !== "disabled" && insights.enabled !== false;
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
  const rejected = insights.rejected;
  const cap = insights.generated_at && insights.items.length
    ? `Generated ${fmtDateTime(insights.generated_at)}${insights.trigger === "refresh" ? " (refreshed)" : ""}${rejected ? ` · ${rejected} rejected by the checks` : ""}`
    : undefined;
  const state = insightState(insights);
  return (
    <Panel
      title="Experimental: cross-item patterns"
      cap={cap}
      right={
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={refresh} disabled={busy || !enabled || insights.status === "refreshing"}
          title={enabled ? "Run pattern analysis again after analyst approvals; the 06:00 version is kept" : "Pattern analysis is not enabled for this Brief"}>
          <RefreshCw className={busy ? "size-3 animate-spin" : "size-3"} /> Refresh insights
        </Button>
      }
    >
      <p className="m-0 mb-2 text-xs text-[#44516a]">{INSIGHTS_CHECK}</p>
      {insights.mock ? <div className="mb-2"><MockTag what="this insights state" /></div> : null}
      {err ? <div className="mb-2"><ErrorNote error={err} /></div> : null}
      {busy || state === "refreshing" ? (
        <div className="flex items-center gap-2 py-3 text-mute" role="status"><Loader2 className="size-4 animate-spin" aria-hidden /> Refreshing pattern analysis…</div>
      ) : state === "failed" ? (
        <Empty>Pattern analysis failed on this run. See <Link href="/health" className="text-jgreen-d hover:underline">Health</Link>.</Empty>
      ) : state ? (
        <Empty>{state}</Empty>
      ) : (
        <>
          <WindowLine w={insights.window} />
          <div className="mb-3 flex items-center gap-1.5 rounded border border-[#f59e0b]/60 bg-[#fff7e6] px-2.5 py-1.5 text-xs font-semibold text-[#8a5a00]">
            <Sparkles className="size-3.5 shrink-0" aria-hidden /> AI-generated — check the cited sources
          </div>
          {insights.status === "partial" ? <div className="mb-2 text-xs text-mute">Fewer than 3 insights passed the checks this time.</div> : null}
          <div className="flex flex-col gap-3">
            {insights.items.map((x) => (
              <InsightCard key={x.insight_id} ins={x} selected={hl === x.insight_id} onSelect={() => setHl(hl === x.insight_id ? null : x.insight_id)} />
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}

/** Why insights can cite items outside the Brief: they read a wider window. Every value comes from the API's
 * insights.window (the window the generator actually used); nothing is shown when it isn't served. */
function WindowLine({ w }: { w: BriefInsights["window"] }) {
  if (!w?.days) return null;
  const span = w.from && w.to ? ` (${fmtDate(w.from)}–${fmtDate(w.to)}${w.stories != null ? `, ${w.stories} ${w.stories === 1 ? "story" : "stories"}` : ""})` : "";
  return (
    <p className="m-0 mb-2 text-xs text-mute">
      Patterns across items from the last {w.days} days{span}, so they can cite items outside today&apos;s Brief.
    </p>
  );
}

/** One insight per row. Always visible: type, top importance, story count, title, summary, why it matters.
 * The claims with their quotes and sources sit behind "Show evidence" (D50: each cited item keeps its score and link). */
function InsightCard({ ins, selected, onSelect }: { ins: Insight; selected: boolean; onSelect: () => void }) {
  const top = SCORE_COLOR[ins.max_score ?? 0]?.[0] ?? "#e3e8ef";
  const [open, setOpen] = useState(false);
  const cited = useMemo(() => {
    const m = new Map<string, CitedItemRow>();
    for (const c of ins.cited_items ?? []) if (!m.has(c.item_id)) m.set(c.item_id, c);
    return m;
  }, [ins.cited_items]);
  const n = ins.claims.length;
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onSelect}
      onKeyDown={(e) => e.target === e.currentTarget && (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect())}
      className={`flex cursor-pointer flex-col gap-2 rounded-md border bg-card px-4 py-3 transition-colors hover:border-jgreen ${selected ? "border-jgreen ring-1 ring-jgreen" : "border-line"}`}
      style={{ borderLeft: `4px solid ${top}` }}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Tag>{label(PATTERN_LABEL, ins.pattern)}</Tag>
        {ins.max_score ? <span className="text-xs text-mute">top importance {ins.max_score}</span> : null}
        <span className="text-xs text-mute">
          · {ins.story_ids.length} {ins.story_ids.length === 1 ? "story" : "stories"}
          {ins.item_ids.length !== ins.story_ids.length ? `, ${ins.item_ids.length} ${ins.item_ids.length === 1 ? "item" : "items"}` : ""}
        </span>
      </div>
      <h3 className="m-0 text-sm font-semibold">{ins.title}</h3>
      <p className="m-0 text-[#44516a]">{ins.summary}</p>
      {ins.why_it_matters ? <p className="m-0 text-xs text-mute"><b className="font-semibold text-ink">Why it matters: </b>{ins.why_it_matters}</p> : null}
      {n ? (
        <div>
          <button type="button" aria-expanded={open} onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
            className="inline-flex items-center gap-1 text-xs font-semibold text-jgreen-d hover:underline">
            {open ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
            {open ? "Hide evidence" : `Show evidence (${n} ${n === 1 ? "claim" : "claims"})`}
          </button>
          {open ? (
            <ul className="m-0 mt-2 flex list-none flex-col gap-3 p-0">
              {ins.claims.map((c, k) => <ClaimBlock key={k} c={c} cited={cited} />)}
            </ul>
          ) : null}
        </div>
      ) : null}
      {ins.baseline_note ? <div className="text-[11px] text-mute">{ins.baseline_note}</div> : null}
    </div>
  );
}

/** A claim, its quote, then one source line per item it cites. The quoted item comes first. */
function ClaimBlock({ c, cited }: { c: Claim; cited: Map<string, CitedItemRow> }) {
  const ids = [...new Set([c.quote_item_id, ...c.item_ids].filter(Boolean))];
  return (
    <li className="flex flex-col gap-1 text-xs">
      <div>{c.text}</div>
      {c.quote ? (
        <blockquote className="m-0 border-l-2 border-line pl-2 italic text-mute">&ldquo;{c.quote}&rdquo;</blockquote>
      ) : null}
      {c.jfrog_quote ? (
        <blockquote className="m-0 border-l-2 border-jgreen pl-2 text-mute">
          <span className="italic">&ldquo;{c.jfrog_quote}&rdquo;</span>
          <span className="not-italic"> — JFrog capability sheet</span>
        </blockquote>
      ) : null}
      {ids.map((id) => <SourceLine key={id} id={id} row={cited.get(id)} />)}
    </li>
  );
}

/** Score, title (opens the drawer), "not in this Brief" when it applies, link to the source. When the API didn't
 * serve the row, the item is fetched (same SWR key as the drawer); in_brief is then unknown and no tag is shown. */
function SourceLine({ id, row }: { id: string; row?: CitedItemRow }) {
  const drawer = useItemDrawer();
  const q = useApi<ItemDetail>(row ? null : `/api/v1/items/${encodeURIComponent(id)}`);
  const it = row ?? q.data?.item;
  const title = it ? it.title : q.error ? `Item ${id.slice(0, 8)} (couldn't load)` : `Item ${id.slice(0, 8)}…`;
  return (
    <div className="flex items-start gap-1.5">
      <ScoreBadge score={it?.score ?? null} />
      <button type="button" onClick={(e) => { e.stopPropagation(); drawer.open(id); }}
        className="min-w-0 text-left font-medium hover:text-jgreen-d hover:underline" title="Open the item">
        {title}
        {row && !row.in_brief ? (
          <Tag className="ml-1.5 align-middle text-[10px] font-normal"
            title={row.score != null && row.score < 3 ? "Scored below the Brief's 3+ line; still a published item" : "Published, but not in this Brief's list (outside its window)"}>
            not in this Brief
          </Tag>
        ) : null}
      </button>
      {it?.url ? (
        <span onClick={(e) => e.stopPropagation()} className="shrink-0">
          <ExtLink href={it.url} className="text-mute hover:text-jgreen-d"><ExternalLink className="mt-0.5 size-3" aria-label="Open the source" /></ExtLink>
        </span>
      ) : null}
    </div>
  );
}
