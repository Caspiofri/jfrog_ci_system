"use client";
import { Suspense } from "react";
import { Async, Empty, ErrorNote, KpiTile, Loading, PageHead, Panel, Tag } from "@/components/ci";
import { FilterSelect } from "@/components/FilterSelect";
import { ChangeDetection, Coverage, EvalCards, Extraction, Funnel, SilentAlert, SilentTable, SourcesTable } from "@/components/health/parts";
import { path, useApi } from "@/lib/api";
import { LEVEL_LABEL, delta, fmtDateTime, fmtLongDate, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import { useUrlState } from "@/lib/useParams";
import type { Brief, BriefRow, Health, Kpi, Page, RunInfo } from "@/lib/types";

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
  const q = useApi<Health>(path("/health", { run_id: runId || undefined }));
  return (
    <>
      <PageHead
        title="Health"
        sub="Does the system run, and is it correct"
        tools={runs.data?.items.length ? (
          <FilterSelect ariaLabel="Run" allLabel="Latest daily run" value={runId} onChange={(v) => set({ run: v })} className="h-8 min-w-[16rem] bg-white text-[13px]"
            options={runs.data.items.map((r) => ({ value: r.run_id, label: `${fmtDateTime(r.started_at)} · ${r.kind} · ${r.status}` }))} />
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
                {h.run.fingerprint ? <span>· fingerprint {h.run.fingerprint}</span> : null}
                {h.run.error ? <span className="text-[#a32d2d]">· {h.run.error}</span> : null}
              </div>
            ) : null}

            {h.silent_sources ? <SilentAlert s={h.silent_sources} /> : null}

            <BriefCounts served={(h as Health & { brief?: ServedCounts }).brief} />

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
              {h.extraction ? <Extraction e={h.extraction} /> : <Empty>No extraction data.</Empty>}
            </Panel>

            <Panel title="How accurate is the system?" cap="Single labeler · golden set">
              {h.eval ? <EvalCards ev={h.eval} /> : <Empty>No eval report yet.</Empty>}
            </Panel>

            <div className="grid items-start gap-3.5 lg:grid-cols-2">
              <Panel title="Do we miss real events?" cap="Coverage check · counts with n, not a rate">
                {h.coverage ? <Coverage cv={h.coverage} /> : <Empty>No coverage check yet.</Empty>}
              </Panel>
              <Panel title="Did the tracked pages change?" cap="Head-to-head change detection">
                {h.change_detection ? <ChangeDetection c={h.change_detection} /> : <Empty>No change-detection run yet.</Empty>}
              </Panel>
            </div>
          </>
        )}
      </Async>
    </>
  );
}

const KPI_LABEL: Record<string, string> = {
  items: "Published in the Brief",
  important: "Rated 4 or 5",
  found_late: "Found late",
  mentions_jfrog: "Mention JFrog",
};

type ServedCounts = { date: string; kpis: Kpi[]; prev_anchor_kind?: string | null };

/** Operational counts that left the Brief (D44): from /health `brief` when served (BACKEND_REQUESTS.md 3g),
 * else the latest Brief's `kpis`. Each with the previous Brief, except when that was the initial import: a
 * 14-day backfill isn't a day, so its delta would mislead. The import is known from `anchor_kind`, never the date. */
function BriefCounts({ served }: { served?: ServedCounts }) {
  const { data: meta } = useMeta();
  const date = served ? null : meta?.latest_brief_date;
  const q = useApi<Brief>(date ? path("/brief", { date, limit: 1 }) : null);
  const briefs = useApi<Page<BriefRow>>(path("/briefs", { limit: 200 }));
  const src = served ?? (q.data ? { date: q.data.date, kpis: q.data.kpis } : null);
  const rows = briefs.data?.items ?? [];
  const i = src ? rows.findIndex((r) => r.date === src.date) : -1;
  const prevRow = i >= 0 ? rows[i + 1] : undefined; // newest first
  const prevKind = served?.prev_anchor_kind ?? prevRow?.anchor_kind ?? (prevRow?.backfill ? "import" : undefined);
  const prevIsImport = prevKind === "import";
  const error = q.error ?? briefs.error;
  return (
    <Panel title="How did the latest Brief's counts move?"
      cap={src ? `Brief of ${fmtLongDate(src.date)} · ${prevIsImport ? "the previous Brief was the initial import, so no comparison" : "vs the previous Brief"}` : undefined}>
      {error ? <ErrorNote error={error} onRetry={() => { q.mutate(); briefs.mutate(); }} /> : !src || (!served && !briefs.data) ? (
        meta && !meta.latest_brief_date ? <Empty>No Brief yet.</Empty> : <Loading rows={1} />
      ) : (
        <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
          {src.kpis.map((k) => {
            const d = delta(k.value, k.prev);
            const sub = prevIsImport
              ? <span className="text-mute" title={`The initial 14-day import had ${k.prev ?? "—"}; a backfill isn't comparable with one day`}>previous Brief was the initial import</span>
              : <span className={d.cls}>{d.text}</span>;
            return <KpiTile key={k.key} value={k.value} label={KPI_LABEL[k.key] ?? k.key} sub={sub} />;
          })}
        </div>
      )}
    </Panel>
  );
}
