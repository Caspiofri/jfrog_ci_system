"use client";
// Health blocks (contract §9). Every eval number carries its n; coverage is counts with n, never a rate.
import { CompetitorLabel } from "@/components/CompetitorAvatar";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Empty, ItemTitle, N, Tag } from "@/components/ci";
import { SOURCE_LABEL, fmtDate, fmtDateTime, label } from "@/lib/format";
import { ageLabel, hasCoverageCounts, measuredLabel, missedState } from "@/lib/healthMeasures";
import { competitorName, useMeta } from "@/lib/meta";
import type { EvalCard, ExtractionBlock, ExtractionRow, Health, Liveness, RunInfo, RunMetrics, RunStep, TestEval } from "@/lib/types";
import { cn } from "@/lib/utils";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
const num = (v: unknown) => (typeof v === "number" ? v : 0);

// ---- funnel ----

const FUNNEL: [string, string, string][] = [
  ["Collected", "collected", "#3f5b8f"],
  ["After dedupe", "kept", "#5b7bb5"],
  ["Not noise", "scored", "#7fa0d4"],
  ["Published", "published", "#41be57"],
  ["Held for review", "held_for_review", "#f59e0b"],
];

export function Funnel({ totals }: { totals: Record<string, number> }) {
  const max = Math.max(1, num(totals.collected));
  return (
    <div className="flex flex-col gap-2">
      {FUNNEL.map(([l, k, c]) => (
        <div key={k} className="grid grid-cols-[8rem_minmax(0,1fr)] items-center gap-3">
          <span className="text-xs text-mute">{l}</span>
          <div className="flex h-7 min-w-9 items-center rounded-[3px] pl-2.5 font-semibold text-white tabular-nums"
            style={{ width: `${Math.max((100 * num(totals[k])) / max, 6)}%`, background: c }}>
            {num(totals[k])}
          </div>
        </div>
      ))}
    </div>
  );
}

const SOURCE_COLS: [string, string][] = [
  ["collected", "Collected"], ["dup_url", "Dup URL"], ["dup_embedding", "Dup similar"], ["kept", "Kept"],
  ["noise", "Noise"], ["scored", "Scored"], ["published", "Published"], ["held_for_review", "Held"],
];

export function SourcesTable({ sources }: { sources: NonNullable<Health["funnel"]>["sources"] }) {
  const th = "border-b border-line px-2.5 py-2 text-right text-xs font-semibold text-mute";
  const td = "border-b border-line px-2.5 py-2 text-right tabular-nums";
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead><tr><th className={cn(th, "text-left")}>Source</th>{SOURCE_COLS.map(([, h]) => <th key={h} className={th}>{h}</th>)}</tr></thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.source}>
              <td className={cn(td, "text-left")}>{label(SOURCE_LABEL, s.source)}{Array.isArray(s.errors) && s.errors.length ? <Tag className="ml-2 bg-[#fdeaea] text-[#a32d2d]">{s.errors.length} errors</Tag> : null}</td>
              {SOURCE_COLS.map(([k]) => <td key={k} className={cn(td, k === "published" && "font-semibold text-jgreen-d")}>{num(s[k])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- silent sources ----

export function SilentAlert({ s }: { s: NonNullable<Health["silent_sources"]> }) {
  const bad = s.items.filter((x) => x.status !== "healthy");
  if (!bad.length) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-line border-l-[3px] border-l-jgreen bg-card px-4 py-3">
        <CheckCircle2 className="size-4 text-jgreen-d" />
        <b className="font-semibold">Every source delivered</b>
        <span className="text-mute">· {s.items.length} sources · {s.label}{s.insufficient_history ? " (too few runs to judge silence)" : ""}</span>
      </div>
    );
  }
  return (
    <div role="alert" className="flex flex-wrap items-center gap-2 rounded-md border border-line border-l-[3px] border-l-[#d14343] bg-[#fff5f5] px-4 py-3">
      <AlertTriangle className="size-4 text-[#d14343]" />
      <b className="font-semibold">{bad.length} silent source{bad.length === 1 ? "" : "s"}</b>
      <span className="text-mute">· {bad.map((x) => `${label(SOURCE_LABEL, x.source)} (${x.status}, ${x.hours_silent ?? "?"} h)`).join("  ·  ")}</span>
    </div>
  );
}

export function SilentTable({ s }: { s: NonNullable<Health["silent_sources"]> }) {
  const td = "border-b border-line px-2.5 py-2";
  return (
    <>
      <table className="w-full border-collapse">
        <thead><tr>{["Source", "Hours", "Last run", "Status"].map((h) => <th key={h} className="border-b border-line px-2.5 py-2 text-left text-xs font-semibold text-mute">{h}</th>)}</tr></thead>
        <tbody>
          {s.items.map((x) => (
            <tr key={x.source}>
              <td className={td}>{label(SOURCE_LABEL, x.source)}</td>
              <td className={`${td} tabular-nums`} title={x.last_item ? `Last item ${fmtDateTime(x.last_item)}` : undefined}>{x.hours_silent ?? "—"}</td>
              <td className={`${td} tabular-nums`}>{x.collected_last_run} collected</td>
              <td className={td}>
                <span className="inline-flex items-center gap-1.5 text-xs">
                  <i className="inline-block size-2 rounded-full" style={{ background: x.status === "healthy" ? "#41be57" : x.status === "critical" ? "#9b1c1c" : "#e5483b" }} />
                  {x.status === "healthy" ? "Healthy" : x.status === "critical" ? "Critical" : "Silent"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 text-[11px] text-mute">{s.label}. Rule: {s.rule}.</div>
    </>
  );
}

// ---- extraction ----

const STATUS_PARTS: [keyof ExtractionRow["by_status"], string, string][] = [
  ["full", "Full text", "#2e9b44"],
  ["partial", "Partial", "#8fd19e"],
  ["snippet", "Snippet only", "#f59e0b"],
  ["junk", "Junk", "#e5483b"],
];

function StatusBar({ r }: { r: ExtractionRow }) {
  return (
    <div className="flex h-2.5 gap-px overflow-hidden rounded-sm bg-track" role="img"
      aria-label={STATUS_PARTS.map(([k, l]) => `${l} ${r.by_status[k]}`).join(", ")}>
      {STATUS_PARTS.map(([k, l, c]) => r.by_status[k] ? (
        <i key={k} title={`${l}: ${r.by_status[k]}`} className="block h-full" style={{ width: `${(100 * r.by_status[k]) / Math.max(1, r.n)}%`, background: c }} />
      ) : null)}
    </div>
  );
}

function FetchReasons({ fetch }: { fetch?: Record<string, number> }) {
  const entries = Object.entries(fetch ?? {}).filter(([, v]) => v);
  if (!entries.length) return null;
  if (entries.length === 1 && entries[0][0] === "not_recorded") {
    return <div className="text-[11px] text-mute">Why a fetch failed isn&apos;t recorded for these items yet (older runs).</div>;
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      <span className="text-mute">Fetch outcome:</span>
      {entries.sort((a, b) => b[1] - a[1]).map(([k, v]) => <Tag key={k}>{k.replace(/_/g, " ")} {v}</Tag>)}
    </div>
  );
}

function ExtractionTable({ rows, keyLabel, fmtKey }: { rows: ExtractionRow[]; keyLabel: string; fmtKey?: (k: string) => string }) {
  const td = "border-b border-line px-2.5 py-1.5 align-middle";
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          {[keyLabel, "Text status", "Extracted"].map((h, i) => (
            <th key={h} className={cn("border-b border-line px-2.5 py-2 text-left text-xs font-semibold text-mute", i === 2 && "text-right")}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key}>
            <td className={`${td} max-w-[14rem] truncate`} title={r.key}>{fmtKey ? fmtKey(r.key) : r.key}</td>
            <td className={`${td} w-[45%]`}><StatusBar r={r} /></td>
            <td className={`${td} whitespace-nowrap text-right tabular-nums`}>
              <b className="font-semibold">{pct(r.rate)}</b> <span className="text-xs text-mute">{r.extracted} of</span><N n={r.n} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const TOP_PUBLISHERS = 12;

export function Extraction({ e }: { e: NonNullable<Health["extraction"]> }) {
  const [scope, setScope] = useState<"run" | "all">("run");
  const [allPubs, setAllPubs] = useState(false);
  const b: ExtractionBlock | null = e[scope];
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded border border-line p-0.5" role="radiogroup" aria-label="Scope">
          {(["run", "all"] as const).map((k) => (
            <button key={k} type="button" role="radio" aria-checked={scope === k} onClick={() => setScope(k)}
              className={cn("rounded-[3px] px-2.5 py-1 text-xs", scope === k ? "bg-navy text-white" : "text-mute hover:text-ink")}>
              {k === "run" ? "This run" : "All stored items"}
            </button>
          ))}
        </div>
        {b ? (
          <span>
            <b className="text-xl font-semibold tabular-nums">{pct(b.rate)}</b>
            <span className="ml-1.5 text-mute">extracted · {b.extracted} of</span><N n={b.n} />
          </span>
        ) : <span className="text-mute">Not measured for this scope.</span>}
        <span className="flex-1" />
        <span className="flex flex-wrap gap-x-3 text-[11px] text-mute">
          {STATUS_PARTS.map(([k, l, c]) => (
            <span key={k} className="inline-flex items-center gap-1"><i className="inline-block size-2 rounded-sm" style={{ background: c }} />{l}</span>
          ))}
        </span>
      </div>
      {!b || !b.n ? <Empty>No kept items in this scope.</Empty> : (
        <>
          <FetchReasons fetch={b.fetch} />
          <div className="grid items-start gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-1 text-xs font-semibold text-mute">By source</h3>
              <ExtractionTable rows={b.by_source} keyLabel="Source" fmtKey={(k) => label(SOURCE_LABEL, k)} />
            </div>
            <div>
              <h3 className="mb-1 text-xs font-semibold text-mute">By publisher · most items first</h3>
              <ExtractionTable rows={allPubs ? b.by_publisher : b.by_publisher.slice(0, TOP_PUBLISHERS)} keyLabel="Publisher" />
              {b.by_publisher.length > TOP_PUBLISHERS ? (
                <Button variant="outline" size="sm" className="mt-2 h-7 text-xs" onClick={() => setAllPubs(!allPubs)}>
                  {allPubs ? "Show top publishers only" : `Show all ${b.by_publisher.length} publishers`}
                </Button>
              ) : null}
            </div>
          </div>
        </>
      )}
      <div className="text-[11px] text-mute">{e.definition}.</div>
    </div>
  );
}

// ---- eval ----

const METRIC_LABEL: Record<string, string> = {
  competitor_accuracy: "Competitor accuracy",
  category_accuracy: "Category accuracy",
  noise_precision: "Noise precision",
  noise_recall: "Noise recall",
  score_exact: "Score exact",
  score_within_1: "Score within 1",
  important_precision: "Important precision (4–5)",
  important_recall: "Important recall (4–5)",
  mentions_jfrog_precision: "Mentions JFrog precision",
  mentions_jfrog_recall: "Mentions JFrog recall",
  funding_m_and_a: "Funding/M&A",
};

export function MetricCards({ cards }: { cards: EvalCard[] }) {
  return (
    <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
      {cards.map((c) => (
        <div key={c.metric} className={cn("rounded-md border border-line bg-card px-4 py-3", c.untested && "bg-page")}>
          <div className="text-[26px] font-semibold leading-tight tabular-nums">
            {c.untested ? <span className="text-mute">—</span> : pct(c.value)}
            <N n={c.n} />
          </div>
          <div className="mt-0.5 text-mute">{METRIC_LABEL[c.metric] ?? c.metric.replace(/_/g, " ")}</div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {c.untested ? <Tag className="bg-track">untested</Tag> : null}
            {c.weak && !c.untested ? <Tag className="bg-[#fff4e0] text-[#8a5a00]" title="n < 10, or an important-item metric">weak evidence</Tag> : null}
          </div>
          {c.note ? <div className="mt-1.5 text-[11px] text-mute">{c.note}</div> : null}
        </div>
      ))}
    </div>
  );
}

export function EvalCards({ ev, missing }: { ev: NonNullable<Health["eval"]>; missing: string }) {
  if (ev.status !== "ok") return <Empty>{missing}</Empty>;
  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-mute">
        {measuredLabel(ev.created_at, fmtDateTime)} · report {ev.report} · split <b className="text-ink">{ev.split}</b> · {ev.live ? "live" : "offline"}
        {ev.n !== undefined ? <> · items scored<N n={ev.n} /></> : null}
        {ev.model ? ` · ${ev.model}` : ""}
        {ev.labels ? <> · golden labels<N n={ev.labels.total} /> ({ev.labels.non_noise} non-noise, {ev.labels.important} rated 4–5, {ev.labels.funding_m_and_a} Funding/M&amp;A)</> : null}
      </div>
      {ev.test_eval_run === false ? (
        <div className="rounded border-l-[3px] border-[#f59e0b] bg-[#fffaf0] px-3 py-2 text-xs">
          The test-split eval hasn&apos;t run yet. These numbers are not the reported ones.
        </div>
      ) : null}
      <MetricCards cards={ev.cards} />
    </div>
  );
}

// ---- coverage ----

function Count({ l, c }: { l: string; c?: { captured: number; n: number } }) {
  if (!c) return null;
  return (
    <div className="rounded-md border border-line px-4 py-3">
      <div className="text-[22px] font-semibold tabular-nums">{c.captured} of {c.n}<N n={c.n} /></div>
      <div className="text-mute">{l}</div>
    </div>
  );
}

export function Coverage({ cv, missing }: { cv: NonNullable<Health["coverage"]>; missing: string }) {
  if (cv.status !== "ok" || !hasCoverageCounts(cv)) return <Empty>{missing}</Empty>;
  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-mute">
        {measuredLabel(cv.measured_on, (d) => fmtDate(d, true))}
        {cv.window ? ` · events ${cv.window.first} to ${cv.window.last}` : ""}{cv.list ? ` · list: ${cv.list}` : ""}{cv.run_id ? ` · run ${cv.run_id}` : ""}
      </div>
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,10rem),1fr))]">
        <Count l="Events captured" c={cv.overall} />
        <Count l={`Important captured (≥ ${cv.important?.min_score ?? 4})`} c={cv.important} />
        {Object.entries(cv.by_source_kind ?? {}).map(([k, v]) => <Count key={k} l={k === "external" ? "From external sources" : k === "feed" ? "From feeds we collect" : k} c={v} />)}
      </div>
      {missedState(cv.missed) === "list" ? (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-mute">Missed</h3>
          {cv.missed!.map((m) => (
            <div key={m.id} className="border-t border-line py-1.5 text-xs first:border-t-0">
              <ItemTitle title={m.title} url={m.official_url} />
              <span className="text-mute"> · <CompetitorLabel k={m.competitor} /> · expected importance {m.expected_importance}</span>
            </div>
          ))}
        </div>
      ) : missedState(cv.missed) === "none" ? <div className="text-xs text-mute">Nothing on the list was missed.</div> : null}
    </div>
  );
}

// ---- change detection ----

export function ChangeDetection({ c, missing }: { c: NonNullable<Health["change_detection"]>; missing: string }) {
  const { data: meta } = useMeta();
  if (c.status === "none") return <Empty>{missing}</Empty>;
  return (
    <div className="flex flex-col gap-2">
      <div>
        <b className="text-xl font-semibold tabular-nums">{c.fetched ?? "—"} of {c.pages ?? "—"}</b>
        <span className="ml-1.5 text-mute">pages fetched · {c.changes ?? 0} changes</span>
      </div>
      <div className="text-xs text-mute">
        {measuredLabel(c.started_at, fmtDateTime)}{ageLabel(c.age_hours) ? ` (${ageLabel(c.age_hours)})` : ""} · run {c.run_id} · {c.live ? "live" : "offline"}
      </div>
      {c.failures?.length ? (
        <div className="text-xs">
          <b className="font-semibold text-[#a32d2d]">{c.failures.length} fetch failures</b>
          {c.failures.map((f, i) => <div key={i} className="text-mute">{[f.competitor, f.page, f.reason ?? f.error].filter(Boolean).join(" · ")}</div>)}
        </div>
      ) : null}
      {c.unconfirmed?.length ? (
        <div className="text-xs">
          <b className="font-semibold">Not confirmed on the page</b>
          {c.unconfirmed.map((u, i) => (
            <div key={i} className="text-mute">{competitorName(meta, u.competitor)} · {u.page}: {Object.entries(u.reasons).map(([a, r]) => `${a.replace(/_/g, " ")} (${r})`).join("; ")}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ---- run history and liveness (D48, contract §11.2) ----

/** One look per marker: ok green, degraded amber, failed / stale / overdue red. */
export const MARKER: Record<string, { label: string; color: string; bg: string; text: string; tip: string }> = {
  ok: { label: "OK", color: "#41be57", bg: "#eef7f0", text: "#1f7a33", tip: "Every step finished" },
  degraded: { label: "Degraded", color: "#f59e0b", bg: "#fff4e0", text: "#8a5a00", tip: "The run finished, but some items fell back (see its steps)" },
  running: { label: "Running", color: "#5b7bb5", bg: "#e8eefb", text: "#3f5b8f", tip: "Started under an hour ago and still running" },
  failed: { label: "Failed", color: "#d14343", bg: "#fdeaea", text: "#a32d2d", tip: "The run stopped; the step it stopped at is marked" },
  stale: { label: "Stale", color: "#9b1c1c", bg: "#fdeaea", text: "#9b1c1c", tip: "Still marked running more than an hour after it started: killed or hung" },
  overdue: { label: "Overdue", color: "#9b1c1c", bg: "#fdeaea", text: "#9b1c1c", tip: "No daily run has started in the expected time" },
  none: { label: "No daily run", color: "#8a94a6", bg: "#eef1f5", text: "#44516a", tip: "The store has no daily run yet" },
};

export function MarkerTag({ marker, title }: { marker: string | null | undefined; title?: string }) {
  const m = MARKER[marker ?? ""] ?? { label: marker ?? "—", color: "#8a94a6", bg: "#eef1f5", text: "#44516a", tip: "" };
  return (
    <span title={title ?? m.tip} className="inline-flex items-center gap-1.5 rounded-[3px] px-2 py-px text-xs font-semibold" style={{ background: m.bg, color: m.text }}>
      <i className="inline-block size-2 rounded-full" style={{ background: m.color }} aria-hidden />
      {m.label}
    </span>
  );
}

/** Is the daily run alive? Overdue shows here because a run that never started leaves no row. */
export function LivenessAlert({ l }: { l: Liveness }) {
  const good = l.state === "ok";
  const warn = l.state === "degraded" || l.state === "running";
  const hours = l.hours_since_latest != null ? `${l.hours_since_latest} h ago` : null;
  const text =
    l.state === "overdue" ? `No daily run has started for ${l.hours_since_latest ?? "?"} h (expected within ${l.overdue_after_hours} h)`
    : l.state === "none" ? "No daily run yet"
    : l.state === "stale" ? "The latest daily run is stuck: still running more than an hour after it started"
    : l.state === "failed" ? "The latest daily run failed"
    : l.state === "degraded" ? "The latest daily run finished degraded"
    : l.state === "running" ? "A daily run is in progress"
    : "The latest daily run finished";
  return (
    <div role={good || warn ? undefined : "alert"}
      className={cn("flex flex-wrap items-center gap-2 rounded-md border border-line border-l-[3px] px-4 py-3",
        good ? "border-l-jgreen bg-card" : warn ? "border-l-[#f59e0b] bg-[#fffaf0]" : "border-l-[#d14343] bg-[#fff5f5]")}>
      {good ? <CheckCircle2 className="size-4 text-jgreen-d" /> : warn ? <Clock className="size-4 text-[#8a5a00]" /> : <AlertTriangle className="size-4 text-[#d14343]" />}
      <b className="font-semibold">{text}</b>
      <MarkerTag marker={l.state} />
      <span className="text-mute">
        {l.latest_run_id ? `· ${l.latest_run_id}` : ""}{hours && l.state !== "overdue" ? ` · started ${hours}` : ""}
        {l.stale_run_ids.length ? ` · stuck: ${l.stale_run_ids.join(", ")}` : ""}
      </span>
    </div>
  );
}

const STEP_COLOR: Record<string, string> = { ok: "#41be57", degraded: "#f59e0b", failed: "#d14343", skipped: "#8a94a6" };

function StepChip({ s }: { s: RunStep }) {
  const extra = [
    s.seconds != null ? `${s.seconds} s` : null,
    s.llm_calls ? `${s.llm_calls} LLM calls` : null,
    s.item_ids?.length ? `${s.item_ids.length} items fell back` : null,
    s.reason ? s.reason : null,
  ].filter(Boolean).join(" · ");
  return (
    <span className="inline-flex items-center gap-1.5 rounded-[3px] border border-line bg-white px-2 py-0.5 text-xs" title={`${s.step}: ${s.status}${extra ? ` · ${extra}` : ""}`}>
      <i className="inline-block size-2 rounded-full" style={{ background: STEP_COLOR[s.status] ?? "#8a94a6" }} aria-hidden />
      <b className="font-semibold">{s.step}</b>
      <span className="text-mute">{s.status === "ok" ? (s.seconds != null ? `${Math.round(s.seconds)} s` : "ok") : s.status}</span>
    </span>
  );
}

/** The run list, newest first, with each run's marker. Picking a row selects that run for the whole page. */
export function RunHistory({ runs, selected, metrics, onSelect }: {
  runs: RunInfo[]; selected: string | null; metrics: RunMetrics | null | undefined; onSelect: (runId: string) => void;
}) {
  const th = "border-b border-line px-2.5 py-2 text-left text-xs font-semibold text-mute";
  const td = "border-b border-line px-2.5 py-2 align-top";
  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse">
          <thead><tr>{["Started (Israel time)", "Kind", "Status", "Duration", "LLM calls", "Run"].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
          <tbody>
            {runs.map((r) => {
              const on = r.run_id === selected;
              const mins = r.finished_at ? Math.round((Date.parse(r.finished_at) - Date.parse(r.started_at)) / 60000) : null;
              return (
                <tr key={r.run_id} className={cn("cursor-pointer hover:bg-page", on && "bg-[#f3fbf4]")} onClick={() => onSelect(r.run_id)}
                  aria-selected={on} tabIndex={0} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(r.run_id))}>
                  <td className={cn(td, "tabular-nums", on && "font-semibold")}>{fmtDateTime(r.started_at)}</td>
                  <td className={td}><Tag>{r.kind}</Tag></td>
                  <td className={td}><MarkerTag marker={r.marker ?? r.status} /></td>
                  <td className={cn(td, "tabular-nums text-mute")}>{mins == null ? "—" : `${mins} min`}</td>
                  <td className={cn(td, "tabular-nums text-mute")}>{r.llm_calls ?? "—"}</td>
                  <td className={cn(td, "font-mono text-[11px] text-mute")}>{r.run_id}{r.error ? <div className="font-sans text-[#a32d2d]">{r.error}</div> : null}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div>
        <div className="mb-1.5 text-xs font-semibold text-mute">Steps of the selected run</div>
        {metrics?.steps?.length ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {metrics.steps.map((s, i) => <StepChip key={`${s.step}-${i}`} s={s} />)}
            {metrics.metadata?.commit ? <span className="text-[11px] text-mute">· commit {String(metrics.metadata.commit).slice(0, 7)}</span> : null}
          </div>
        ) : (
          <div className="text-xs text-mute">No step record for this run (runs before Oct 31 night have none).</div>
        )}
        {metrics?.error ? <div className="mt-1 text-xs text-[#a32d2d]">{metrics.error}</div> : null}
      </div>
    </div>
  );
}

/** The test-split eval: the reported numbers. A slot with its three facts (n, date, fingerprint) until it runs. */
export function TestEvalBlock({ t, missing }: { t: TestEval | null | undefined; missing: string }) {
  const ran = t?.status === "ok";
  if (!ran) return <Empty>{missing}</Empty>;
  const fact = (k: string, v: React.ReactNode) => (
    <div className="rounded-md border border-line bg-card px-4 py-3">
      <div className="text-lg font-semibold tabular-nums">{v}</div>
      <div className="text-xs text-mute">{k}</div>
    </div>
  );
  return (
    <div className="flex flex-col gap-3">
      {t.test_runs && t.test_runs > 1 ? (
        <div role="alert" className="rounded border-l-[3px] border-[#d14343] bg-[#fff5f5] px-3 py-2 text-xs">
          The test split has been evaluated {t.test_runs} times; it should run once. The newest report is shown.
        </div>
      ) : null}
      <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
        {fact("Items scored (n)", t.n ?? "Not recorded")}
        {fact("Measured on", t.created_at ? fmtDateTime(t.created_at) : "Not recorded")}
        {fact("Fingerprint", t.fingerprint ? <span className="font-mono text-sm">{t.fingerprint}</span> : "Not recorded")}
        {t.model ? fact("Model", <span className="text-sm">{t.model}</span>) : null}
      </div>
      {t.cards?.length ? <MetricCards cards={t.cards} /> : null}
      {t.report ? <div className="text-[11px] text-mute">Report {t.report}</div> : null}
    </div>
  );
}
