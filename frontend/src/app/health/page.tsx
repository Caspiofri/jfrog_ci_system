"use client";
import { Suspense } from "react";
import { Async, Empty, ErrorNote, KpiTile, Loading, PageHead, Panel, Tag, UnverifiedNote } from "@/components/ci";
import { FilterSelect } from "@/components/FilterSelect";
import { ChangeDetection, Coverage, EvalCards, Extraction, Funnel, LivenessAlert, MARKER, RunHistory, SilentAlert, SilentTable, SourcesTable, TestEvalBlock } from "@/components/health/parts";
import { path, useApi, useRecord } from "@/lib/api";
import { LEVEL_LABEL, delta, fmtDateTime, fmtLongDate, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import { briefForRun } from "@/lib/healthBrief";
import { noDataReason } from "@/lib/healthReasons";
import { useUrlState } from "@/lib/useParams";
import type { Brief, BriefRow, Health, Page, RunInfo } from "@/lib/types";

export default function HealthPage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <HealthScreen />
    </Suspense>
  );
}

function HealthScreen() {
  const { get, set } = useUrlState();
  const runId = get("run");
  const runs = useApi<Page<RunInfo>>(path("/runs", { limit: 50 }));
  // a chosen run: shown only when the response is that run; the latest run (no choice) has nothing to match
  const q = useRecord<Health>(path("/health", { run_id: runId || undefined }), runId || "latest", (d) => (runId ? d.run?.run_id : "latest"));
  const { data: meta } = useMeta();
  const missing = noDataReason(meta?.meta?.mode);
  return (
    <>
      <PageHead
        title="Health"
        info="Does the system run, and is it correct?"
        tools={runs.data?.items.length ? (
          <FilterSelect ariaLabel="Run" allLabel="Latest daily run" value={runId} onChange={(v) => set({ run: v })} className="h-8 min-w-[16rem] bg-white text-[0.8125rem]"
            options={runs.data.items.map((r) => ({ value: r.run_id, label: `${fmtDateTime(r.started_at)} · ${r.kind} · ${MARKER[r.marker ?? r.status]?.label ?? r.status}` }))} />
        ) : null}
      />
      {runs.error ? <ErrorNote error={runs.error} onRetry={() => runs.mutate()} /> : null}
      <Async {...q} retry={() => q.mutate()} rows={8}>
        {(h) => (
          <>
            {h.run ? (
              <div className="-mt-2 flex flex-wrap items-center gap-2 text-xs text-mute">
                <span>Run {h.run.run_id}</span>
                <Tag>{h.run.kind}</Tag>
                <Tag className={h.run.status === "ok" ? "bg-[#eef7f0] text-jgreen-d" : "bg-[#fdeaea] text-[#a32d2d]"}>{h.run.status}</Tag>
                <span>{fmtDateTime(h.run.started_at)} → {fmtDateTime(h.run.finished_at)}</span>
                {h.run.model ? <span>· {h.run.model}</span> : null}
                {h.run.llm_calls !== null && h.run.llm_calls !== undefined ? <span>· {h.run.llm_calls} LLM calls</span> : null}
                {h.run.fingerprint ? <span>· {runId ? "this run's" : "latest run's"} fingerprint <span className="font-mono">{h.run.fingerprint}</span></span> : null}
                {h.run.error ? <span className="text-[#a32d2d]">· {h.run.error}</span> : null}
              </div>
            ) : null}

            {h.liveness ? <LivenessAlert l={h.liveness} /> : null}
            {h.silent_sources ? <SilentAlert s={h.silent_sources} /> : null}

            <Panel title="Did each run finish?" cap="Newest first · pick a run to see its numbers below">
              {runs.data?.items.length ? (
                <RunHistory runs={runs.data.items} selected={runId || h.run?.run_id || null} metrics={h.run_metrics} onSelect={(v) => set({ run: v })} />
              ) : runs.error ? <Empty>The run history could not be loaded.</Empty> : runs.data ? <Empty>No runs yet.</Empty> : <Loading rows={2} />}
            </Panel>

            <BriefCounts runId={runId} />

            <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]">
              <Panel title="Where do items drop off?" cap={h.funnel ? `All sources, this run · published and held at ${label(LEVEL_LABEL, h.funnel.level)}` : undefined}>
                {h.funnel ? <Funnel totals={h.funnel.totals} /> : <Empty>No funnel for this run.</Empty>}
              </Panel>
              <Panel title="Which sources went quiet?">
                {h.silent_sources?.items.length ? <SilentTable s={h.silent_sources} /> : <Empty>No source history yet.</Empty>}
              </Panel>
            </div>

            <Panel title="Which sources deliver value?" cap="Collected vs published, this run">
              {h.funnel?.sources.length ? <SourcesTable sources={h.funnel.sources} /> : <Empty>No sources in this run.</Empty>}
            </Panel>

            <Panel title="Do we get the article text?" cap="Full or partial page text, per source and publisher">
              {h.extraction ? <Extraction e={h.extraction} /> : <Empty>{missing}</Empty>}
            </Panel>

            <Panel title="What does the held-out test split say?" cap="The reported accuracy · runs once, on a frozen system">
              <TestEvalBlock t={h.test_eval} missing={missing} />
            </Panel>

            <Panel title="How accurate is the system?" cap="Single labeler · golden set · newest eval of any split">
              {h.eval ? <EvalCards ev={h.eval} missing={missing} /> : <Empty>{missing}</Empty>}
            </Panel>

            <div className="grid items-start gap-3.5 lg:grid-cols-2">
              <Panel title="Do we miss real events?" cap="Coverage check · counts with n, not a rate">
                {h.coverage ? <Coverage cv={h.coverage} missing={missing} /> : <Empty>{missing}</Empty>}
              </Panel>
              <Panel title="Did the tracked pages change?" cap="Head-to-head change detection">
                <UnverifiedNote className="mb-3" />
                {h.change_detection ? <ChangeDetection c={h.change_detection} missing={missing} /> : <Empty>{missing}</Empty>}
              </Panel>
            </div>
          </>
        )}
      </Async>
    </>
  );
}

type Tile = { key: string; label: string; value: number; prev: number | null };

/** The Brief's counts on Health: the Brief of the run picked in the Run filter, or the latest Brief. "Published" and "rated 4–5" come from the Brief's summary (scored 3+, the
 * same numbers the Brief shows); the previous Brief's from its /briefs row. Found late and Mentions JFrog are the
 * operational counts that left the Brief: they still come from `kpis` and count every published score.
 * No delta when the previous Brief was the initial import: a 14-day backfill isn't comparable with one day. */
function BriefCounts({ runId }: { runId: string }) {
  const { data: meta } = useMeta();
  const briefs = useApi<Page<BriefRow>>(path("/briefs", { limit: 200 }));
  const { date, picked } = briefForRun(briefs.data?.items ?? [], runId, meta?.latest_brief_date);
  const q = useRecord<Brief>(date ? path("/brief", { date, limit: 1 }) : null, date, (b) => b.date);
  const b = q.data;
  const rows = briefs.data?.items ?? [];
  const i = b ? rows.findIndex((r) => r.date === b.date) : -1;
  const prevRow = i >= 0 ? rows[i + 1] : undefined; // newest first
  const prevIsImport = (prevRow?.anchor_kind ?? (prevRow?.backfill ? "import" : undefined)) === "import";
  const kpi = (k: string) => b?.kpis?.find((x) => x.key === k);
  const tiles: Tile[] = b?.summary ? [
    { key: "published", label: `Published in the Brief (scored ${b.summary.brief_min_score}+)`, value: b.summary.published, prev: prevRow?.published ?? null },
    { key: "published_high", label: "Of those, rated 4 or 5", value: b.summary.published_high, prev: prevRow?.published_high ?? null },
    { key: "found_late", label: "Found late (any published score)", value: kpi("found_late")?.value ?? 0, prev: kpi("found_late")?.prev ?? null },
    { key: "mentions_jfrog", label: "Mention JFrog (any published score)", value: kpi("mentions_jfrog")?.value ?? 0, prev: kpi("mentions_jfrog")?.prev ?? null },
  ] : [];
  const error = q.error ?? briefs.error;
  return (
    <Panel title={picked ? "How did this run's Brief counts move?" : "How did the latest Brief's counts move?"}
      cap={b ? `Brief of ${fmtLongDate(b.date)} · ${prevIsImport ? "the previous Brief was the initial import, so no comparison" : "vs the previous Brief"}` : undefined}>
      {error ? <ErrorNote error={error} onRetry={() => { q.mutate(); briefs.mutate(); }} /> : picked && briefs.data && date === null ? (
        <Empty>This run has no Brief of its own.</Empty>
      ) : !b || !briefs.data ? (
        meta && !meta.latest_brief_date ? <Empty>No Brief yet.</Empty> : <Loading rows={1} />
      ) : !tiles.length ? (
        <Empty>No counts for the Brief of {fmtLongDate(b.date)}.</Empty>
      ) : (
        <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
          {tiles.map((k) => {
            const d = delta(k.value, k.prev);
            const sub = prevIsImport
              ? <span className="text-mute" title={`The initial 14-day import had ${k.prev ?? "—"}; a backfill isn't comparable with one day`}>previous Brief was the initial import</span>
              : <span className={d.cls}>{d.text}</span>;
            return <KpiTile key={k.key} value={k.value} label={k.label} sub={sub} />;
          })}
        </div>
      )}
    </Panel>
  );
}
