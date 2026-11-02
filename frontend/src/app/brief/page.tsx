"use client";
import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight, Loader2, Newspaper, RefreshCw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ArticleLink, Async, Empty, ErrorNote, Hint, ImportanceLegend, ItemTitle, Loading, PageHead, Panel, Tag } from "@/components/ci";
import { cn } from "@/lib/utils";
import { FilterSelect } from "@/components/FilterSelect";
import { useItemDrawer } from "@/components/ItemDrawer";
import { BriefCard, MockTag } from "@/components/brief/BriefCard";
import { ApiError, path, send, useApi, useRecord } from "@/lib/api";
import { PATTERN_LABEL, SCORE_COLOR, fmtDate, fmtDateTime, fmtLongDate, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import { MOCK, mockBrief, useMock } from "@/lib/mock";
import { useUrlState } from "@/lib/useParams";
import type { Brief, BriefInsights, BriefRow, BriefSummary, CitedItemRow, Claim, Insight, ItemDetail, Page, RunMetrics } from "@/lib/types";
import { runCountsFor, todayTiles } from "@/lib/briefNumbers";
import { CAPABILITY_ROWS } from "@/lib/capabilityRows";
import { CAPABILITY_NAME, claimCapability, insightCapabilities } from "@/lib/capabilitySheet";
import { insightsTitle } from "@/lib/insightsTitle";
import { CONTINUITY_TIP, continuityBadge, goneLine } from "@/lib/continuity";

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

  const raw = useRecord<Brief>(
    briefs.data ? path("/brief", { date: date || undefined, competitor, category, limit: all ? PAGE : TOP, offset: all ? offset : 0 }) : null,
    date, (b) => b.date,
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
        icon={<Newspaper className="size-5 text-jgreen-d" aria-hidden />}
        titleHint={DAILY_BRIEF_HINT}
        sub={
          <span className="mt-1 flex items-center gap-2">
            <Button variant="outline" size="icon" className="size-7" disabled={!older} onClick={() => go(older)} aria-label="Previous Brief">
              <ChevronLeft className="size-4" />
            </Button>
            <Hint text={brief.data?.window ? (backfill
              ? "The 14-day import that started the store. Everything in it was published before the first run, so \"Found late\" badges are hidden here."
              : `Everything discovered from ${fmtDateTime(brief.data.window.prev_anchor)} to ${fmtDateTime(brief.data.window.anchor)} Israel time (${brief.data.window.hours} h).`) : null}
              className="min-w-[13rem] text-center">{date ? fmtLongDate(date) : briefs.isLoading ? "Loading…" : "No Brief yet"}</Hint>
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

      <ImportanceLegend className="-mt-2" />

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
                <SummaryBlock date={b.date} s={b.summary} runId={b.window.anchor_run_id} />

                <InsightsPanel date={b.date} insights={b.insights} hl={hl} setHl={setHl} onRefreshed={() => brief.mutate()} />

                <Panel
                  big
                  title="What was published in this Brief?"
                  cap={`Sorted by importance · ${b.items.total} ${b.items.total === 1 ? "item" : "items"}${competitor || category ? " match the filters" : ""}`}
                  info={`The items found in this Brief's window and rated ${b.brief_min_score ?? 3} or higher on importance, published automatically or approved by an analyst. Items still waiting in the Review queue aren't listed.`}
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
              </>
            )
          }
        </Async>
      ) : null}
    </>
  );
}

/** "Today in numbers": four tiles, each number straight from the API, each explained on hover. */
function SummaryBlock({ date, s, runId }: { date: string; s: BriefSummary; runId: string }) {
  // keepPreviousData off: a 404 for this run must not leave the previous Brief's count on screen
  const run = useApi<RunMetrics>(path(`/run-metrics/${encodeURIComponent(runId)}`), { shouldRetryOnError: false, keepPreviousData: false });
  const tiles = todayTiles(s, runCountsFor(runId, run.data));
  return (
    <section aria-label="Today in numbers">
      <h2 className="m-0 mb-2 text-sm font-semibold">Today in numbers{s.mock ? <MockTag what="these counts" /> : null}</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {tiles.map((t) => {
          const body = (
            <>
              <span className="block text-xs text-mute">{t.label}</span>
              <b className={cn("block text-2xl font-semibold tabular-nums", t.key === "review" && t.value ? "text-[#8a5a00]" : "")}>
                {t.value ?? (t.key === "new" && run.isLoading ? "…" : "—")}
              </b>
              {t.key === "review" && t.value ? (
                <span className="mt-0.5 inline-flex items-center gap-1 text-xs font-semibold text-jgreen-d"><ArrowRight className="size-3.5" aria-hidden /> Review these</span>
              ) : null}
            </>
          );
          const box = "block rounded-md border border-line bg-card px-4 py-3 text-left";
          return t.key === "review" && t.value ? (
            <Hint key={t.key} text={<>{t.hint} Click to review them.</>} asChild>
              <Link href={`/review?brief=${encodeURIComponent(date)}`} data-tile={t.key} className={cn(box, "transition-colors hover:border-jgreen")}>{body}</Link>
            </Hint>
          ) : (
            <Hint key={t.key} text={t.hint} className={box}><span data-tile={t.key}>{body}</span></Hint>
          );
        })}
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

/** Hover texts for the Brief title and the insights AI label (the analyst check of 1 Nov lives in AI_HINT). */
const DAILY_BRIEF_HINT = "Everything new since the previous Brief, ranked by importance.";
const AI_LABEL = "AI-generated — check the cited sources";
const AI_HINT =
  "AI-written summary that connects several stories. Checked on a small sample (1 Nov: 4 insights, 12 claims): facts were well supported (11 of 12 claims), but some conclusions were stronger than the evidence. Open the cited sources before sharing.";


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
      big
      title={
        <span className="inline-flex items-center gap-2">
          {insightsTitle(insights.window)}
          <AiLabel />
        </span>
      }
      cap={cap}
      info={windowText(insights.window)}
      right={
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={refresh} disabled={busy || !enabled || insights.status === "refreshing"}
          title={enabled ? "Run pattern analysis again after analyst approvals; the 06:00 version is kept" : "Pattern analysis is not enabled for this Brief"}>
          <RefreshCw className={busy ? "size-3 animate-spin" : "size-3"} /> Refresh insights
        </Button>
      }
    >
      {goneLine(insights.previous) ? <p className="m-0 mb-2 text-xs text-ink" data-gone-line>{goneLine(insights.previous)}</p> : null}
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
 * insights.window (the window the generator actually used); nothing when it isn't served. Shown on hover. */
function windowText(w: BriefInsights["window"]): string | undefined {
  if (!w?.days) return undefined;
  const span = w.from && w.to ? ` (${fmtDate(w.from)}–${fmtDate(w.to)}${w.stories != null ? `, ${w.stories} ${w.stories === 1 ? "story" : "stories"}` : ""})` : "";
  return `Patterns across items from the last ${w.days} days${span}, so they can cite items outside today's Brief.`;
}

/** One insight per row. Always visible: type, top importance, title, summary, why it matters (no story count: the evidence lists them).
 * The claims with their quotes and sources sit behind "Show evidence" (D50: each cited item keeps its score and link). */
function InsightCard({ ins, selected, onSelect }: { ins: Insight; selected: boolean; onSelect: () => void }) {
  const top = SCORE_COLOR[ins.max_score ?? 0]?.[0] ?? "#e3e8ef";
  const [details, setDetails] = useState(false); // collapsed by default: title and chips only
  const [open, setOpen] = useState(false); // the claims, inside the details
  const cited = useMemo(() => {
    const m = new Map<string, CitedItemRow>();
    for (const c of ins.cited_items ?? []) if (!m.has(c.item_id)) m.set(c.item_id, c);
    return m;
  }, [ins.cited_items]);
  const n = ins.claims.length;
  const toggle = () => {
    const next = !details;
    setDetails(next);
    if (next !== selected) onSelect(); // opening highlights its items in the Brief; closing clears it
  };
  const id = `ins-${ins.insight_id}`;
  return (
    <div
      onClick={toggle}
      data-insight={ins.insight_id}
      className={`flex cursor-pointer flex-col gap-2 rounded-md border bg-card px-4 py-3 transition-colors hover:border-jgreen ${selected ? "border-jgreen ring-1 ring-jgreen" : "border-line"}`}
      style={{ borderLeft: `4px solid ${top}` }}
    >
      <div className="flex flex-wrap items-center gap-1.5" data-insight-header>
        <Tag>{label(PATTERN_LABEL, ins.pattern)}</Tag>
        <ContinuityBadge c={ins.continuity} />
        <TouchesJfrog claims={ins.claims} />
      </div>
      <h3 className="m-0 text-sm font-semibold">
        <button type="button" aria-expanded={details} aria-controls={id} onClick={(e) => { e.stopPropagation(); toggle(); }}
          className="inline-flex items-start gap-1 text-left hover:text-jgreen-d">
          {details ? <ChevronDown className="mt-0.5 size-3.5 shrink-0" aria-hidden /> : <ChevronRight className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
          {ins.title}
        </button>
      </h3>
      {details ? (
        <div id={id} className="flex flex-col gap-2" data-insight-details>
          {ins.max_score ? <span className="text-xs text-mute">Top importance of its items: {ins.max_score}</span> : null}
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
                <ul className="m-0 mt-2 flex list-none flex-col gap-3 p-0" onClick={(e) => e.stopPropagation()}>
                  {ins.claims.map((c, k) => <ClaimBlock key={k} c={c} cited={cited} />)}
                </ul>
              ) : null}
            </div>
          ) : null}
          {ins.baseline_note ? <div className="text-[11px] text-mute">{ins.baseline_note}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

/** The one AI label of the insights: sparkles and a visible warning; the check of 1 Nov on hover and keyboard focus. */
function AiLabel() {
  return (
    <Hint text={AI_HINT}>
      <span className="inline-flex items-center gap-1 rounded border border-[#f59e0b]/60 bg-[#fff7e6] px-2 py-0.5 text-xs font-semibold text-[#8a5a00]" data-ai-label>
        <Sparkles className="size-3.5 shrink-0" aria-hidden />
        {AI_LABEL}
      </span>
    </Hint>
  );
}

/** A claim's JFrog quote with the capability it comes from: the claim's own field, or the one sheet row that holds
 *  the quote exactly. With neither, the quote as before, credited to the capability sheet. */
function JfrogQuote({ c }: { c: Claim }) {
  const cap = claimCapability(c, CAPABILITY_ROWS);
  return (
    <div data-jfrog-quote={cap.source}
      className={cap.key ? "rounded-sm border-l-2 border-jgreen bg-[#eef7f0] px-2 py-0.5 text-jgreen-d" : "text-mute"}>
      {cap.key ? (
        <><b className="font-semibold">JFrog {CAPABILITY_NAME[cap.key]}:</b> <span className="italic">&ldquo;{c.jfrog_quote}&rdquo;</span></>
      ) : (
        <><span className="italic">&ldquo;{c.jfrog_quote}&rdquo;</span> — JFrog capability sheet</>
      )}
    </div>
  );
}

/** "Touches JFrog: <capability> · <capability>" in the insight header; nothing when no claim names one. */
function TouchesJfrog({ claims }: { claims: Claim[] }) {
  const caps = insightCapabilities(claims, CAPABILITY_ROWS);
  if (!caps.length) return null;
  return (
    <Tag className="border border-jgreen/40 bg-[#eef7f0] text-[11px] font-semibold text-jgreen-d">
      Touches JFrog: {caps.map((k) => CAPABILITY_NAME[k]).join(" · ")}
    </Tag>
  );
}

const BADGE_STYLE: Record<string, string> = {
  new: "border-[#3f5b8f]/40 bg-[#e8eefb] text-[#3f5b8f]",
  continuing: "border-line bg-page text-ink",
  strengthened: "border-[#1e63a6]/40 bg-[#e3f0fb] text-[#1e63a6]", // sky blue: apart from New (slate blue) and the JFrog greens
};

/** New / Also in previous Brief (<date>) [· +N new sources], from the API's continuity field; nothing when absent. */
function ContinuityBadge({ c }: { c: Insight["continuity"] }) {
  const b = continuityBadge(c, (d) => fmtDate(d));
  if (!b) return null;
  return (
    <Hint text={CONTINUITY_TIP}>
      <Tag className={cn("border text-[11px] font-semibold", BADGE_STYLE[b.status])}>{b.text}</Tag>
    </Hint>
  );
}

/** A cited item's row: served in insights.cited_items, or fetched (same SWR key as the drawer) when it wasn't.
 * A fetched item has no in_brief, so no "not in this Brief" tag is shown for it. */
function useCitedItem(id: string, row?: CitedItemRow) {
  const q = useRecord<ItemDetail>(row || !id ? null : `/api/v1/items/${encodeURIComponent(id)}`, id, (d) => d.item?.item_id);
  const it = row ?? q.data?.item;
  return {
    title: it ? it.title : q.error ? `Item ${id.slice(0, 8)} (couldn't load)` : `Item ${id.slice(0, 8)}…`,
    score: it?.score ?? null,
    url: it?.url ?? null,
    outside: row ? !row.in_brief : false,
    belowLine: row?.score != null && row.score < 3,
  };
}

const SCORE_TIP = "Importance of the cited item";

/** One claim as one block: the quoted item's score down the left side, then the claim, its quote, and its sources.
 * When a claim cites several items, each extra source line carries its own small score. */
function ClaimBlock({ c, cited }: { c: Claim; cited: Map<string, CitedItemRow> }) {
  const ids = [...new Set([c.quote_item_id, ...c.item_ids].filter(Boolean))];
  const main = useCitedItem(ids[0] ?? "", ids[0] ? cited.get(ids[0]) : undefined);
  const [bg, fg] = SCORE_COLOR[main.score ?? 0] ?? SCORE_COLOR[0];
  return (
    <li className="flex gap-2.5 text-xs">
      <span title={SCORE_TIP} className="flex w-7 shrink-0 items-center justify-center self-stretch rounded text-sm font-semibold tabular-nums"
        style={{ background: bg, color: fg }}>
        {main.score ?? "–"}
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <div className="text-[13px] font-semibold text-ink">{c.text}</div>
        {c.quote ? <div className="italic text-mute">&ldquo;{c.quote}&rdquo;</div> : null}
        {c.jfrog_quote ? <JfrogQuote c={c} /> : null}
        {ids.map((id, k) => <SourceLine key={id} id={id} row={cited.get(id)} withScore={k > 0} />)}
      </div>
    </li>
  );
}

/** "Source: <title>" (opens the drawer), "not in this Brief" when it applies, link to the full article. */
function SourceLine({ id, row, withScore }: { id: string; row?: CitedItemRow; withScore: boolean }) {
  const drawer = useItemDrawer();
  const it = useCitedItem(id, row);
  const [bg, fg] = SCORE_COLOR[it.score ?? 0] ?? SCORE_COLOR[0];
  return (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-mute">
      {withScore ? (
        <span title={SCORE_TIP} className="inline-flex h-4 min-w-4 items-center justify-center rounded-[3px] px-1 text-[10px] font-semibold tabular-nums"
          style={{ background: bg, color: fg }}>{it.score ?? "–"}</span>
      ) : null}
      <span>Source:</span>
      <ItemTitle title={it.title} onOpen={() => drawer.open(id)} />
      {it.outside ? (
        <Tag className="text-[10px]"
          title={it.belowLine ? "Scored below the Brief's 3+ line; still a published item" : "Published, but not in this Brief's list (outside its window)"}>
          not in this Brief
        </Tag>
      ) : null}
      <ArticleLink href={it.url} />
    </div>
  );
}
