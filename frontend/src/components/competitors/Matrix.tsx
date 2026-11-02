"use client";
// "JFrog vs competitors", capability first (D75): pick a capability on the left; on the right one row per vendor,
// JFrog first, with what its public page states, the source and the as-of date. Pages that say nothing and vendors
// not tracked yet fold into two muted lines. No comparison, no verdict: colour only marks the data state.
import { useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, Clock } from "lucide-react";
import { ArticleLink, ErrorNote, Panel } from "@/components/ci";
import { CompetitorAvatar } from "@/components/CompetitorAvatar";
import { useRecord } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { buildMatrix, capabilityCount, capabilityRows, type MatrixCell, type MatrixRow } from "@/lib/matrix";
import { useMeta } from "@/lib/meta";
import type { CompetitorProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

export const CAPTION = "What was found on public pages, not a verdict.";
export const NOT_STATED_LINE = "Their page says nothing:";
export const NOT_TRACKED_LINE = "Not tracked yet:";

/** One vendor's row: avatar and name, the value (2 lines, click to expand), source, as-of date; stale gets a clock. */
function VendorRow({ c, k, name, jfrog = false }: { c: MatrixCell; k: string; name: string; jfrog?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={cn("flex flex-col gap-1 border-t border-line px-3 py-2 first:border-t-0 sm:flex-row sm:items-start sm:gap-3", jfrog && "bg-[#f8fbf8]")}
      data-vendor={k} data-state={c.state}>
      <span className="flex w-36 shrink-0 items-center gap-1.5 font-semibold">
        {jfrog ? null : <CompetitorAvatar k={k} name={name} size="md" />}
        {name}
      </span>
      <span className="min-w-0 flex-1">
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} title={open ? "Show less" : "Show all"}
          className={cn("text-left text-[13px] text-ink hover:text-jgreen-d", !open && "line-clamp-2")}>{c.full}</button>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-mute">
          {c.stale ? (
            <span className="inline-flex items-center gap-1 text-[#8a5a00]" title={c.staleReason ?? undefined}>
              <Clock className="size-3" aria-hidden /> Stale{c.asOf ? ` · as of ${fmtDate(c.asOf, true)}` : ""}
            </span>
          ) : c.asOf ? <span>as of {fmtDate(c.asOf, true)}</span> : null}
          <ArticleLink href={c.source} label={`Open ${name}'s source page in a new tab`} />
          {jfrog ? null : <Link href={`/competitors/${encodeURIComponent(k)}#head-to-head`} className="hover:text-jgreen-d hover:underline">Compare on {name}&apos;s profile</Link>}
        </span>
      </span>
    </div>
  );
}

function CapabilityBlock({ r, order, name, title = false }: { r: MatrixRow; order: string[]; name: (k: string) => string; title?: boolean }) {
  const v = capabilityRows(r, order);
  const { n, of } = capabilityCount(r);
  return (
    <section className="min-w-0 rounded-md border border-line" data-capability={r.axis} aria-label={r.label}>
      {title ? <h3 className="m-0 border-b border-line px-3 py-2 text-sm font-semibold">{r.label} <span className="text-xs font-normal text-mute">{n} of {of} pages state something</span></h3> : null}
      <VendorRow c={v.jfrog} k="jfrog" name="JFrog" jfrog />
      {v.listed.map((k) => <VendorRow key={k} c={r.cells[k]} k={k} name={name(k)} />)}
      {v.notStated.length || v.notTracked.length ? (
        <div className="flex flex-col gap-0.5 border-t border-line bg-page px-3 py-2 text-xs text-mute" data-folded>
          {v.notStated.length ? <span>{NOT_STATED_LINE} {v.notStated.map(name).join(", ")}</span> : null}
          {v.notTracked.length ? <span>{NOT_TRACKED_LINE} {v.notTracked.map(name).join(", ")}</span> : null}
        </div>
      ) : null}
    </section>
  );
}

/** Six profile calls (the ones the profile pages make); each shown only when it is that competitor's record. */
export function CapabilityMatrix() {
  const { data: meta } = useMeta();
  const keys = (meta?.competitors ?? []).filter((c) => !c.is_industry && c.key !== "industry").map((c) => c.key).slice(0, 6);
  const q = [0, 1, 2, 3, 4, 5].map((i) => useRecord<CompetitorProfile>(keys[i] ? `/api/v1/competitors/${encodeURIComponent(keys[i])}` : null, keys[i], (d) => d.key)); // eslint-disable-line react-hooks/rules-of-hooks
  const [sel, setSel] = useState(0); // the first capability is open by default
  const [all, setAll] = useState(false);
  const loading = !meta || q.slice(0, keys.length).some((x) => !x.data && !x.error);
  const errors = q.filter((x) => x.error);
  const profiles = keys.map((k, i) => ({ key: k, name: q[i].data?.name ?? k, axes: q[i].data?.head_to_head?.axes }));
  const name = (k: string) => profiles.find((p) => p.key === k)?.name ?? k;
  const rows = buildMatrix(profiles);
  const cur = rows[Math.min(sel, Math.max(0, rows.length - 1))];
  return (
    <Panel title="JFrog vs competitors"
      right={rows.length ? (
        <button type="button" aria-pressed={all} onClick={() => setAll(!all)} className="inline-flex items-center gap-1 text-xs font-semibold text-jgreen-d hover:underline">
          {all ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}{all ? "Show one capability" : "Expand all"}
        </button>
      ) : null}>
      {errors.length ? <div className="mb-2"><ErrorNote error={errors[0].error!} onRetry={() => errors.forEach((x) => x.mutate())} /></div> : null}
      {loading ? <div className="py-4 text-xs text-mute" role="status">Loading the head-to-head data…</div> : !rows.length ? (
        <div className="py-3 text-xs text-mute">No head-to-head data yet.</div>
      ) : all ? (
        <div className="flex flex-col gap-3" data-expand-all>
          {rows.map((r) => <CapabilityBlock key={r.axis} r={r} order={keys} name={name} title />)}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-[15rem_minmax(0,1fr)]">
          <label className="md:hidden">
            <span className="sr-only">Capability</span>
            <select value={sel} onChange={(e) => setSel(Number(e.target.value))} className="h-9 w-full rounded-md border border-line bg-white px-2 text-[13px]">
              {rows.map((r, i) => { const c = capabilityCount(r); return <option key={r.axis} value={i}>{r.label} · {c.n} of {c.of} pages state something</option>; })}
            </select>
          </label>
          <div className="hidden flex-col gap-1 md:flex" role="tablist" aria-label="Capabilities">
            {rows.map((r, i) => {
              const c = capabilityCount(r);
              return (
                <button key={r.axis} type="button" role="tab" aria-selected={i === sel} onClick={() => setSel(i)}
                  className={cn("rounded border px-3 py-2 text-left transition-colors hover:border-jgreen", i === sel ? "border-jgreen bg-accent" : "border-line")}>
                  <span className="block text-[13px] font-semibold">{r.label}</span>
                  <span className="block text-[11px] text-mute">{c.n} of {c.of} pages state something</span>
                </button>
              );
            })}
          </div>
          {cur ? <CapabilityBlock r={cur} order={keys} name={name} /> : null}
        </div>
      )}
      <p className="m-0 mt-2 text-xs text-mute" data-caption>{CAPTION}</p>
    </Panel>
  );
}
