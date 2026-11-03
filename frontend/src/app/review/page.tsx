"use client";
import { CompetitorLabel } from "@/components/CompetitorAvatar";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Check, ChevronDown, Flag, Pencil, Search, ShieldCheck, Undo2, X } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ArticleLink, Async, ColourLegends, Empty, ErrorNote, HBars, Hint, Loading, N, PageHead, Panel, Tag } from "@/components/ci";
import { Donut } from "@/components/Donut";
import { FilterChip, SortControl, StatusControl } from "@/components/review/FilterBar";
import { ItemRow } from "@/components/ItemRow";
import { ItemActions, useRefreshAll } from "@/components/review/actions";
import { ApiError, get, path, send, useApi } from "@/lib/api";
import { competitorFilterOptions } from "@/lib/competitorLabel";
import { LOG_STATUSES, SCORE_OPTIONS, SORT_LINES, SORT_OPTIONS, decidedIds, decisionOptions, filterQueue, flaggedFirst, isActiveFlag, hasLocalFilters, inQueueScope, queueQuery, remainingOffsets, sortQueue, windowOptions, type DecisionView, type QueueSort } from "@/lib/reviewQueue";
import { HOLD_LABEL, LEVEL_LABEL, STATUS_LABEL, fmtDate, fmtDateTime, fmtLongDate, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import { useUrlState } from "@/lib/useParams";
import type { HoldReason, ItemDetail, Level, Log, LogRow, Page, Review, ReviewChangeRow, ReviewItemRow, SourceRow, TrustResult } from "@/lib/types";
import { alwaysReviewedHint, holdChip } from "@/lib/holdReasons";
import { HOLD_RULES, HOLD_RULES_INTRO } from "@/lib/holdRulesText";
import { cn } from "@/lib/utils";

const PAGE = 25;
const LEVEL_HELP: Record<Level, string> = {
  strict: "Every unvetted source is held, plus everything always held",
  balanced: "Unvetted sources held only at importance 4 or 5",
  relaxed: "Only the always-held reasons: pricing, M&A, Mentions JFrog, changed cells, failures",
};

export default function ReviewPage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <ReviewScreen />
    </Suspense>
  );
}

/** Every page of GET /review for these API-side filters, so search and the local filters see the whole queue. */
async function getWholeQueue(url: string): Promise<Review> {
  const first = await get<Review>(url);
  const rest = remainingOffsets(first.total, first.items.length);
  if (!rest.length) return first;
  const pages = await Promise.all(rest.map((o) => get<Review>(url.replace(/([?&])offset=0\b/, `$1offset=${o}`))));
  return { ...first, items: [...first.items, ...pages.flatMap((p) => p.items)] };
}

/** D91: every decided item (approved, dismissed, flagged) from GET /log, all pages, then each item's record
 *  (GET /items/{id}, the drawer's own) so the queue's search, filters and sort apply to it unchanged. */
async function getDecided(url: string): Promise<ReviewItemRow[]> {
  const first = await get<Log>(url);
  const rest = remainingOffsets(first.total, first.items.length);
  const pages = await Promise.all(rest.map((o) => get<Log>(url.replace(/([?&])offset=0\b/, `$1offset=${o}`))));
  const ids = decidedIds([...first.items, ...pages.flatMap((p) => p.items)] as LogRow[]);
  const items = await Promise.all(ids.map((id) => get<ItemDetail>(`/api/v1/items/${encodeURIComponent(id)}`)));
  return items.map((d) => ({ kind: "item" as const, item: d.item, held_since: d.item.discovered_at, trust_source: null }));
}

function ReviewScreen() {
  const { get: param, set } = useUrlState();
  const { data: meta } = useMeta();
  const preview = param("preview") as Level | "";
  const reason = param("reason");
  const competitor = param("competitor");
  const brief = param("brief");
  const score = param("score");
  const category = param("category");
  const viewParam = param("decision");
  const view: DecisionView = viewParam === "approved" || viewParam === "flagged" || viewParam === "dismissed" || viewParam === "all" ? viewParam : "";
  const VIEW_NAME: Record<DecisionView, string> = { "": "Needs decision", approved: "Approved", flagged: "Flagged", dismissed: "Dismissed", all: "All" };
  const sortParam = param("sort");
  const sort: QueueSort = sortParam === "newest" || sortParam === "oldest" ? sortParam : "";
  const offset = Number(param("offset") || 0);
  const [search, setSearch] = useState(param("q"));
  const urlQ = param("q");
  useEffect(() => {
    if (search === urlQ) return;
    const t = setTimeout(() => set({ q: search || null, offset: null }), 250);
    return () => clearTimeout(t);
  }, [search, urlQ, set]);
  const q = useSWR<Review, ApiError>(path("/review", queueQuery({ level: preview, reason, competitor, brief })), getWholeQueue,
    { revalidateOnFocus: false, keepPreviousData: true });
  const briefs = useApi<Page<{ date: string }>>(path("/briefs", { limit: 200 }));
  const decided = useSWR<ReviewItemRow[], ApiError>(path("/log", { status: LOG_STATUSES, competitor, limit: 200, offset: 0 }), getDecided,
    { revalidateOnFocus: false, keepPreviousData: true });
  const current = meta?.level;
  const shown = q.data?.level;
  const previewing = Boolean(preview && current && preview !== current);
  const [trustMsg, setTrustMsg] = useState<TrustResult | null>(null);
  const local = { q: urlQ, score, category };
  const windows = windowOptions((briefs.data?.items ?? []).map((b) => b.date).concat(brief ? [brief] : []), fmtLongDate);

  return (
    <>
      <PageHead title="Review queue" info="Items held by the routing rules, each with the reason it was held." />
      {trustMsg ? <TrustToast res={trustMsg} onDone={() => setTrustMsg(null)} /> : null}

      <Async {...q} retry={() => q.mutate()} rows={6}>
        {(r) => {
          const lv = r.levels.find((x) => x.level === r.level);
          // D91: decided items in the same scope as the API's queue (window, competitor, reason at this level)
          const done = (decided.data ?? []).filter((x) => inQueueScope(x.item, { window: r.scope?.window, reason, level: r.level }));
          const byStatus = (st: string) => done.filter((x) => x.item.status === st);
          const isFlagged = (x: ReviewItemRow | ReviewChangeRow) => isActiveFlag(x);
          // D107: flagged = the boolean on any item that is not dismissed; held ones included (they stay in Needs decision)
          const flaggedRows = [...r.items.filter(isFlagged), ...done.filter(isFlagged)];
          const needs = r.items.length; // what the default lists: held items, plus changed cells outside a Brief window
          const counts = { needs, approved: byStatus("approved").length, flagged: flaggedRows.length, dismissed: byStatus("dismissed").length, all: needs + done.length };
          // Dismissed is offered when the data carries dismissed items (or the URL asks for it, so the selector is never blank)
          const viewOptions = decisionOptions(counts, view === "dismissed" || (decided.data ?? []).some((x) => x.item.status === "dismissed"));
          const base: (ReviewItemRow | ReviewChangeRow)[] = view === "" ? r.items : view === "all" ? [...r.items, ...done] : view === "flagged" ? flaggedRows : byStatus(view);
          const sorted = sortQueue(filterQueue(base, local), sort);
          const rows = view === "" || view === "all" ? flaggedFirst(sorted) : sorted; // flagged items lead the list
          const filtered = hasLocalFilters(local) || reason || competitor || brief;
          const anyFilter = Boolean(brief || score || category || competitor || reason);
          // the header count: "110 of 110 held at Strict", or "Showing 14 of 110 held at Strict" with a filter or search;
          // the whole is the unfiltered queue at this level (backlog_total), never a typed number
          const lvName = label(LEVEL_LABEL, r.level);
          const whole = view === "" ? (filtered ? r.backlog_total ?? r.total : r.total) : (filtered ? counts[view === "all" ? "all" : view] : base.length);
          const what = view === "" ? `held at ${lvName}` : `· ${VIEW_NAME[view]}`;
          const countLine = `${filtered ? "Showing " : ""}${rows.length} of ${whole} ${what}`;
          const pageRows = rows.slice(offset, offset + PAGE);
          return (
            <>
              <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))]">
                <Panel title="How much should the system decide alone?" cap={lv ? <>over non-noise items<N n={lv.n} /></> : undefined}>
                  <LevelControl levels={r.levels} current={current} shown={shown} onPreview={(l) => set({ preview: l === current ? null : l, offset: null })} />
                </Panel>
                <Panel title="How much needs a human?" cap={`at ${label(LEVEL_LABEL, r.level)}`}>
                  {lv ? (
                    <Donut center={lv.held} caption="held" parts={[
                      { label: "Held for review", value: lv.held, color: "#f59e0b" },
                      { label: "Cleared", value: lv.published, color: "#41be57" },
                    ]} />
                  ) : <Empty>No counts.</Empty>}
                </Panel>
                <Panel title="Why are items held?" cap="an item can count twice · click to filter">
                  {Object.keys(r.counts_by_reason).length ? (
                    <div className="flex flex-col">
                      {Object.entries(r.counts_by_reason).sort((a, b) => b[1] - a[1]).map(([code, n]) => (
                        <button key={code} type="button" onClick={() => set({ reason: reason === code ? null : code, offset: null })}
                          className={cn("rounded text-left hover:bg-page", reason === code && "bg-accent")}>
                          <HBars max={Math.max(...Object.values(r.counts_by_reason))} rows={[{ label: label(HOLD_LABEL, code), value: n, color: reason === code ? "var(--jgreen-d)" : undefined }]} />
                        </button>
                      ))}
                    </div>
                  ) : <Empty>Nothing is held at this level.</Empty>}
                </Panel>
              </div>

              {previewing ? (
                <PreviewBar preview={preview as Level} current={current!} onBack={() => set({ preview: null })} />
              ) : null}

              <TrustedSources />

              <ColourLegends />

              <Panel
                title="What needs my decision?"
                info={<HoldRulesInfo />}
                cap={<span data-queue-count>{countLine}</span>}
              >
                {/* row 1, what is shown: status, search, sort */}
                <div className="mb-2 flex flex-wrap items-center gap-2" data-filter-row="shown">
                  <StatusControl ariaLabel="Decision" value={view} onChange={(v) => set({ decision: v || null, offset: null })} options={viewOptions} />
                  {/* flagged items leave the default view; their count stays next to the filter, one click away */}
                  <button type="button" onClick={() => set({ decision: "flagged", offset: null })} data-flagged-count={counts.flagged}
                    className="inline-flex shrink-0 items-center gap-1 text-xs text-mute hover:text-ink hover:underline focus-visible:outline-2 focus-visible:outline-jgreen">
                    <Flag className="size-3.5" aria-hidden /> {counts.flagged} flagged
                  </button>
                  <label className="relative min-w-[14rem] flex-1">
                    <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-mute" />
                    <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search held items"
                      placeholder="Search id, title or publisher"
                      className="h-8 w-full rounded-md border border-line bg-white pr-2.5 pl-8 text-[0.8125rem] outline-none focus:border-jgreen" />
                  </label>
                  <SortControl ariaLabel="Sort" allLabel={SORT_OPTIONS[0].label} value={sort} onChange={(v) => set({ sort: v || null, offset: null })}
                    options={SORT_OPTIONS.slice(1)} />
                </div>
                {/* row 2, filter: chips that wrap together */}
                <div className="mb-2.5 flex flex-wrap items-center gap-1.5" data-filter-row="filter">
                  <span className="mr-0.5 text-xs text-mute">Filter</span>
                  <FilterChip name="Brief day" ariaLabel="Window" allLabel="All held items" value={brief} onChange={(v) => set({ brief: v, offset: null })}
                    options={windows} display={(o) => fmtDate(o.value)} />
                  <FilterChip name="Score" ariaLabel="Score" allLabel="All scores" value={score} onChange={(v) => set({ score: v, offset: null })}
                    options={SCORE_OPTIONS} display={(o) => o.label.replace(/^Score /, "")} />
                  <FilterChip name="Category" ariaLabel="Category" allLabel="All categories" value={category} onChange={(v) => set({ category: v, offset: null })}
                    options={(meta?.categories ?? []).map((c) => ({ value: c, label: c }))} />
                  <FilterChip name="Competitor" ariaLabel="Competitor" allLabel="All competitors" value={competitor} onChange={(v) => set({ competitor: v, offset: null })}
                    options={competitorFilterOptions(meta)} />
                  <FilterChip name="Hold reason" ariaLabel="Hold reason" allLabel="All reasons" value={reason} onChange={(v) => set({ reason: v, offset: null })}
                    options={(meta?.hold_reasons ?? []).map((c) => ({ value: c, label: label(HOLD_LABEL, c) }))} />
                  {anyFilter ? (
                    <button type="button" onClick={() => set({ brief: null, score: null, category: null, competitor: null, reason: null, offset: null })}
                      className="ml-1 text-xs font-semibold text-jgreen-d hover:underline focus-visible:outline-2 focus-visible:outline-jgreen" data-clear-all>Clear all</button>
                  ) : null}
                </div>
                <div className="mb-2 text-xs text-mute">{SORT_LINES[sort]}{brief ? " Changed cells belong to no Brief, so a Brief window lists items only." : ""}</div>
                {previewing ? <div className="mb-2 text-xs text-mute">Actions are off while previewing another level.</div> : null}
                {pageRows.length ? (
                  pageRows.map((row) =>
                    row.kind === "item" && row.item.status !== "awaiting_review" ? (
                      <DecidedItem key={row.item.item_id} row={row} level={r.level} />
                    ) : row.kind === "item" ? (
                      <QueueItem key={row.item.item_id} row={row} level={r.level} disabled={previewing} onTrusted={setTrustMsg} />
                    ) : (
                      <ChangeRow key={`c${row.change_id}`} row={row} disabled={previewing} />
                    ),
                  )
                ) : filtered ? (
                  <Empty>
                    Nothing held matches {urlQ.trim() ? <>&ldquo;{urlQ.trim()}&rdquo; with </> : null}these filters
                    {brief ? <> in the Brief of {fmtLongDate(brief)}. <button type="button" className="font-semibold text-jgreen-d hover:underline" onClick={() => set({ brief: null, offset: null })}>Search all held items</button></> : "."}{" "}
                    An item already approved or dismissed is no longer held: find it in the <Link href="/log" className="font-semibold text-jgreen-d hover:underline">Log</Link>.
                  </Empty>
                ) : (
                  <Empty>{view === "approved" || view === "flagged" || view === "dismissed" ? `No ${VIEW_NAME[view].toLowerCase()} items in this scope.` : `The queue is empty at ${label(LEVEL_LABEL, r.level)}.`}</Empty>
                )}
                {rows.length > PAGE ? (
                  <div className="mt-2.5 flex items-center justify-end gap-2">
                    <span className="text-xs text-mute">{offset + 1}–{Math.min(offset + PAGE, rows.length)} of {rows.length}</span>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset === 0} onClick={() => set({ offset: String(Math.max(0, offset - PAGE)) })}>Previous</Button>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset + PAGE >= rows.length} onClick={() => set({ offset: String(offset + PAGE) })}>Next</Button>
                  </div>
                ) : null}
              </Panel>
            </>
          );
        }}
      </Async>
    </>
  );
}

function LevelControl({ levels, current, shown, onPreview }: {
  levels: Review["levels"]; current: Level | undefined; shown: Level | undefined; onPreview: (l: Level) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5" role="radiogroup" aria-label="Autonomy level">
      {levels.map((l) => (
        <Hint key={l.level} text={LEVEL_HELP[l.level]} asChild>
        <button type="button" role="radio" aria-checked={shown === l.level} onClick={() => onPreview(l.level)}
          className={cn("flex items-center gap-3 rounded border px-3 py-2 text-left transition-colors hover:border-jgreen",
            shown === l.level ? "border-jgreen bg-accent" : "border-line")}>
          <span className="flex flex-1 items-center gap-1.5">
            <span className="font-semibold">{label(LEVEL_LABEL, l.level)}</span>
            {current === l.level ? <Tag className="bg-jgreen px-1.5 text-[0.6875rem] text-white">current</Tag> : null}
          </span>
          <span className="text-right">
            <b className="text-lg font-semibold tabular-nums">{l.held}</b>
            <span className="block text-[0.6875rem] text-mute">held</span>
          </span>
        </button>
        </Hint>
      ))}
    </div>
  );
}

function PreviewBar({ preview, current, onBack }: { preview: Level; current: Level; onBack: () => void }) {
  const refresh = useRefreshAll();
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const apply = async () => {
    setErr(null);
    try {
      await send("PUT", "/api/v1/settings/autonomy-level", { level: preview });
      setConfirm(false);
      onBack();
      await refresh();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-[#f59e0b] bg-[#fffaf0] px-4 py-2.5">
      <span className="flex-1">
        Previewing <b>{label(LEVEL_LABEL, preview)}</b>. Nothing has changed; the current level is still <b>{label(LEVEL_LABEL, current)}</b>.
      </span>
      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onBack}>Back to {label(LEVEL_LABEL, current)}</Button>
      <Button size="sm" className="h-7 text-xs" onClick={() => setConfirm(true)}>Set {label(LEVEL_LABEL, preview)} as the level</Button>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change the autonomy level to {label(LEVEL_LABEL, preview)}?</DialogTitle>
            <DialogDescription>
              Items held only for reasons that {label(LEVEL_LABEL, preview)} doesn&apos;t hold are cleared at once. Items an analyst already decided keep their decision.
            </DialogDescription>
          </DialogHeader>
          {err ? <ErrorNote error={err} /> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(false)}>Cancel</Button>
            <Button onClick={apply}>Set {label(LEVEL_LABEL, preview)}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** The (i) on "What needs my decision?": why items are held, in plain words. */
function HoldRulesInfo() {
  return (
    <span className="block">
      <span className="mb-1.5 block">{HOLD_RULES_INTRO}</span>
      <span className="m-0 flex flex-col gap-0.5">
        {HOLD_RULES.map(([code, v]) => (
          <span key={code} className="block">• <b className="font-semibold">{label(HOLD_LABEL, code)}:</b> {v}</span>
        ))}
      </span>
    </span>
  );
}

function ReasonChips({ reasons, level }: { reasons: HoldReason[]; level: Level }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {reasons.map((h) => {
        const chip = holdChip(h, label(HOLD_LABEL, h.code));
        const always = chip.levels == null;
        const active = h.held_at.includes(level);
        return (
          <span key={h.code} title={chip.hint || undefined}
            className={cn("inline-flex items-center gap-1 rounded-[3px] border px-2 py-px text-xs",
              always ? "border-[#e5483b] bg-[#fff5f5] text-[#a32d2d]" : active ? "border-[#f59e0b] bg-[#fffaf0] text-[#8a5a00]" : "border-line text-mute")}>
            <b className="font-semibold">{chip.label}</b>
            {chip.levels ? <span>· {chip.levels}</span> : null}
          </span>
        );
      })}
    </div>
  );
}

/** D91: an item that is not held (approved, dismissed, or a flagged cleared item) under Approved, Flagged, Dismissed or
 *  All: its status, no actions (nothing here changes a decision; Reopen stays in the item's side panel). A flagged item
 *  carries the Flagged badge from ItemRow (D107). */
function DecidedItem({ row, level }: { row: ReviewItemRow; level: Level }) {
  const it = row.item;
  return (
    <ItemRow item={it} showBadge={false}
      actions={<Tag className="text-xs font-semibold" data-decision={it.status}>{label(STATUS_LABEL, it.status)}</Tag>}
      extra={<ReasonChips reasons={it.hold_reasons} level={level} />} />
  );
}

function QueueItem({ row, level, disabled, onTrusted }: { row: ReviewItemRow; level: Level; disabled: boolean; onTrusted: (r: TrustResult) => void }) {
  const [err, setErr] = useState<ApiError | null>(null);
  const it = row.item;
  const ts = row.trust_source;
  const unvetted = it.hold_reasons.some((h) => h.code === "unvetted_source");
  return (
    <ItemRow
      item={it}
      showBadge={false}
      actions={<ItemActions item={it} disabled={disabled} onError={setErr} />}
      extra={
        <>
          <ReasonChips reasons={it.hold_reasons} level={level} />
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-mute">
            <span>Held since {fmtDateTime(row.held_since)}</span>
            {it.confidence != null ? <span>· confidence {it.confidence.toFixed(2)}</span> : null}
            {unvetted && ts && !ts.vetted ? (
              <TrustButton host={ts.host} fromItem={it.item_id} suggest={ts.suggest} approved={ts.approved} dismissed={ts.dismissed} disabled={disabled} onDone={onTrusted} onError={setErr} />
            ) : null}
          </div>
          {err ? <div className="mt-1.5"><ErrorNote error={err} /></div> : null}
        </>
      }
    />
  );
}

function TrustButton({ host, fromItem, suggest, approved, dismissed, disabled, onDone, onError }: {
  host: string; fromItem: string; suggest: boolean; approved: number; dismissed: number; disabled: boolean;
  onDone: (r: TrustResult) => void; onError: (e: ApiError | null) => void;
}) {
  const refresh = useRefreshAll();
  const [busy, setBusy] = useState(false);
  const trust = async () => {
    setBusy(true);
    onError(null);
    try {
      const res = await send<TrustResult>("POST", "/api/v1/sources/trust", { host, from_item_id: fromItem });
      onDone(res);
      await refresh();
    } catch (e) {
      onError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span>· {host}: {approved} approved, {dismissed} dismissed</span>
      <Button size="sm" variant="outline" className={cn("h-6 px-2 text-[0.6875rem]", suggest && "border-jgreen text-jgreen-d")} disabled={disabled || busy} onClick={trust}
        title="Add this host to the vetted list in the store; its items stop being held for an unvetted source">
        <ShieldCheck className="size-3" /> Trust this source{suggest ? " (suggested)" : ""}
      </Button>
    </span>
  );
}

function TrustToast({ res, onDone }: { res: TrustResult; onDone: () => void }) {
  const refresh = useRefreshAll();
  const [err, setErr] = useState<ApiError | null>(null);
  const undo = async () => {
    try {
      await send("DELETE", `/api/v1/sources/trust/${encodeURIComponent(res.host)}`);
      await refresh();
      onDone();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <div role="status" className="flex flex-wrap items-center gap-3 rounded-md border border-jgreen bg-[#f3fbf4] px-4 py-2.5">
      <ShieldCheck className="size-4 text-jgreen-d" />
      <span className="flex-1">
        <b>{res.host}</b> is now trusted. {res.released.total} item{res.released.total === 1 ? "" : "s"} released
        {res.still_held.total ? `, ${res.still_held.total} still held for another reason` : ""}.
      </span>
      {err ? <ErrorNote error={err} /> : null}
      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={undo}><Undo2 className="size-3" /> Undo</Button>
      <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onDone}>Close</Button>
    </div>
  );
}

/** Suggested hosts (3+ approvals, 0 dismissals) and the hosts trusted from this screen, with remove. */
function TrustedSources() {
  const refresh = useRefreshAll();
  const suggested = useApi<Page<SourceRow>>(path("/sources", { kind: "suggested", limit: 20 }));
  const vetted = useApi<Page<SourceRow>>(path("/sources", { kind: "vetted", limit: 200 }));
  const [err, setErr] = useState<ApiError | null>(null);
  const trusted = vetted.data?.items.filter((s) => s.group === "trusted") ?? [];
  const act = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <Panel title="Which sources have earned trust?" info="A host is suggested after 3 or more approvals and no dismissals.">
      {err ? <div className="mb-2"><ErrorNote error={err} /></div> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-1 text-xs font-semibold text-mute">Suggested</h3>
          <Async {...suggested} retry={() => suggested.mutate()} rows={2} isEmpty={(d) => !d.items.length}
            empty="No host has 3+ approvals and 0 dismissals yet.">
            {(d) => d.items.map((s) => (
              <div key={s.host} className="flex items-center gap-2 border-t border-line py-1.5 first:border-t-0">
                <span className="flex-1">{s.host} <span className="text-xs text-mute">{s.approved} approved · {s.held} held</span></span>
                <Button size="sm" variant="outline" className="h-6 px-2 text-[0.6875rem]" onClick={() => act(() => send("POST", "/api/v1/sources/trust", { host: s.host }))}>
                  <ShieldCheck className="size-3" /> Trust
                </Button>
              </div>
            ))}
          </Async>
        </div>
        <div>
          <h3 className="mb-1 text-xs font-semibold text-mute">Trusted from this screen</h3>
          <Async {...vetted} retry={() => vetted.mutate()} rows={2} isEmpty={() => !trusted.length}
            empty="None yet. Vetted sources come from a list maintained by the project.">
            {() => trusted.map((s) => (
              <div key={s.host} className="flex items-center gap-2 border-t border-line py-1.5 first:border-t-0">
                <span className="flex-1">{s.host}</span>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-[0.6875rem]" onClick={() => act(() => send("DELETE", `/api/v1/sources/trust/${encodeURIComponent(s.host)}`))}>
                  <Undo2 className="size-3" /> Remove
                </Button>
              </div>
            ))}
          </Async>
        </div>
      </div>
    </Panel>
  );
}

const CHANGE_DISMISS: Record<string, string> = {
  wrong_extraction: "Wrong extraction",
  cosmetic: "Cosmetic change",
  not_a_change: "Not a change",
};

function ChangeRow({ row, disabled }: { row: ReviewChangeRow; disabled: boolean }) {
  const refresh = useRefreshAll();
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(row.new_value ?? "");
  const id = encodeURIComponent(row.change_id);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      setEditing(false);
      await refresh();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const off = disabled || busy;
  return (
    <div className="flex items-start gap-3 border-t border-line bg-[#fff7e6] px-2.5 py-2.5 first:border-t-0">
      <Tag className="bg-[#f59e0b] text-white">Cell</Tag>
      <div className="min-w-0 flex-1">
        <div className="font-semibold"><CompetitorLabel k={row.competitor} /> · {row.axis_label ?? row.axis ?? "axis unknown"}: head-to-head cell changed</div>
        <div className="mt-1 grid gap-2 text-xs md:grid-cols-2">
          <div><div className="text-mute">Was</div>{row.old_value || "—"}{row.old_evidence ? <div className="mt-0.5 italic text-mute">&ldquo;{row.old_evidence}&rdquo;</div> : null}</div>
          <div><div className="text-mute">Now</div>{row.new_value || "—"}{row.new_evidence ? <div className="mt-0.5 italic text-mute">&ldquo;{row.new_evidence}&rdquo;</div> : null}</div>
        </div>
        {row.tier_changes?.length ? (
          <ul className="m-0 mt-1.5 list-none p-0 text-xs">
            {row.tier_changes.map((t, i) => (
              <li key={i}><b className="font-semibold">{t.tier}</b> {t.change}{t.old_name ? ` (was ${t.old_name})` : ""}: {t.old || "—"} → {t.new || "—"}</li>
            ))}
          </ul>
        ) : null}
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-mute">
          {row.held_since ? <span>Detected {fmtDateTime(row.held_since)}</span> : null}
          {row.page_url ? <ArticleLink href={row.page_url} label="Open the tracked page in a new tab" /> : null}
          <span title={alwaysReviewedHint("changed_cell", "")}>Always reviewed: changed head-to-head cell</span>
        </div>
        {editing ? (
          <div className="mt-2 flex flex-col gap-1.5">
            <Textarea value={value} onChange={(e) => setValue(e.target.value)} rows={2} aria-label="Corrected cell value" className="bg-white" />
            <div className="flex gap-1.5">
              <Button size="sm" className="h-7 text-xs" disabled={off || !value.trim()} onClick={() => run(() => send("PATCH", `/api/v1/changes/${id}`, { value }))}>Save value</Button>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          </div>
        ) : null}
        {err ? <div className="mt-1.5"><ErrorNote error={err} /></div> : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
        <Button size="sm" variant="outline" className="h-7 border-jgreen px-2.5 text-xs text-jgreen-d hover:bg-jgreen hover:text-white" disabled={off}
          onClick={() => run(() => send("POST", `/api/v1/changes/${id}/approve`, {}))}>
          <Check className="size-3.5" /> Approve
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs" disabled={off}><X className="size-3.5" /> Dismiss <ChevronDown className="size-3" /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel className="text-xs text-mute">Dismiss restores the old value</DropdownMenuLabel>
            {Object.entries(CHANGE_DISMISS).map(([k, v]) => (
              <DropdownMenuItem key={k} onSelect={() => run(() => send("POST", `/api/v1/changes/${id}/dismiss`, { reason: k }))}>{v}</DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs" disabled={off} onClick={() => setEditing(true)}><Pencil className="size-3.5" /> Edit</Button>
      </div>
    </div>
  );
}
