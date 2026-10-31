"use client";
// Health blocks (contract §9). Every eval number carries its n; coverage is counts with n, never a rate.
import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Empty, ExtLink, N, Tag } from "@/components/ci";
import { SOURCE_LABEL, fmtDateTime, label } from "@/lib/format";
import { competitorName, useMeta } from "@/lib/meta";
import type { ExtractionBlock, ExtractionRow, Health } from "@/lib/types";
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
        ) : null}
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

export function EvalCards({ ev }: { ev: NonNullable<Health["eval"]> }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-mute">
        {ev.status === "ok" ? (
          <>
            Report {ev.report} · {fmtDateTime(ev.created_at)} · split <b className="text-ink">{ev.split}</b> · {ev.live ? "live" : "offline"}
            {ev.n !== undefined ? <> · items scored<N n={ev.n} /></> : null}
            {ev.model ? ` · ${ev.model}` : ""}
          </>
        ) : "No eval report yet."}
        {ev.labels ? <> · golden labels<N n={ev.labels.total} /> ({ev.labels.non_noise} non-noise, {ev.labels.important} rated 4–5, {ev.labels.funding_m_and_a} Funding/M&amp;A)</> : null}
      </div>
      {ev.test_eval_run === false ? (
        <div className="rounded border-l-[3px] border-[#f59e0b] bg-[#fffaf0] px-3 py-2 text-xs">
          The test-split eval hasn&apos;t run yet (D23). These numbers are not the reported ones.
        </div>
      ) : null}
      <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr))]">
        {ev.cards.map((c) => (
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

export function Coverage({ cv }: { cv: NonNullable<Health["coverage"]> }) {
  const { data: meta } = useMeta();
  if (cv.status !== "ok") return <Empty>No coverage check has run yet.</Empty>;
  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-mute">
        Events {cv.window?.first} to {cv.window?.last} · list: {cv.list} · run {cv.run_id}
      </div>
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,10rem),1fr))]">
        <Count l="Events captured" c={cv.overall} />
        <Count l={`Important captured (≥ ${cv.important?.min_score ?? 4})`} c={cv.important} />
        {Object.entries(cv.by_source_kind ?? {}).map(([k, v]) => <Count key={k} l={k === "external" ? "From external sources" : k === "feed" ? "From feeds we collect" : k} c={v} />)}
      </div>
      {cv.missed?.length ? (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-mute">Missed</h3>
          {cv.missed.map((m) => (
            <div key={m.id} className="border-t border-line py-1.5 text-xs first:border-t-0">
              <ExtLink href={m.official_url}>{m.title}</ExtLink>
              <span className="text-mute"> · {competitorName(meta, m.competitor)} · expected importance {m.expected_importance}</span>
            </div>
          ))}
        </div>
      ) : <div className="text-xs text-mute">Nothing on the list was missed.</div>}
    </div>
  );
}

// ---- change detection ----

export function ChangeDetection({ c }: { c: NonNullable<Health["change_detection"]> }) {
  const { data: meta } = useMeta();
  if (c.status === "none") return <Empty>No change-detection run yet.</Empty>;
  return (
    <div className="flex flex-col gap-2">
      <div>
        <b className="text-xl font-semibold tabular-nums">{c.fetched ?? "—"} of {c.pages ?? "—"}</b>
        <span className="ml-1.5 text-mute">pages fetched · {c.changes ?? 0} changes</span>
      </div>
      <div className="text-xs text-mute">
        Run {c.run_id} · {fmtDateTime(c.started_at)} · {c.live ? "live" : "offline"} · {c.age_hours !== undefined ? `${c.age_hours} h ago` : ""}
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
