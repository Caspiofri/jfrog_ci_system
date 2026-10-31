"use client";
import { Suspense } from "react";
import { Async, Empty, ErrorNote, Loading, PageHead, Panel, Tag } from "@/components/ci";
import { FilterSelect } from "@/components/FilterSelect";
import { ChangeDetection, Coverage, EvalCards, Extraction, Funnel, SilentAlert, SilentTable, SourcesTable } from "@/components/health/parts";
import { path, useApi } from "@/lib/api";
import { LEVEL_LABEL, fmtDateTime, label } from "@/lib/format";
import { useUrlState } from "@/lib/useParams";
import type { Health, Page, RunInfo } from "@/lib/types";

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

            <Panel title="How accurate is the system?" cap="Single labeler · golden set (D17, D23)">
              {h.eval ? <EvalCards ev={h.eval} /> : <Empty>No eval report yet.</Empty>}
            </Panel>

            <div className="grid items-start gap-3.5 lg:grid-cols-2">
              <Panel title="Do we miss real events?" cap="Coverage check · counts with n, not a rate">
                {h.coverage ? <Coverage cv={h.coverage} /> : <Empty>No coverage check yet.</Empty>}
              </Panel>
              <Panel title="Did the tracked pages change?" cap="Head-to-head change detection (D13)">
                {h.change_detection ? <ChangeDetection c={h.change_detection} /> : <Empty>No change-detection run yet.</Empty>}
              </Panel>
            </div>
          </>
        )}
      </Async>
    </>
  );
}
