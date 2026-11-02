"use client";
// "JFrog vs competitors": every capability row, JFrog first, then the six tracked competitors. Values as the
// head-to-head data holds them; no comparison, no verdict (the analyst draws the conclusion).
import { ArticleLink, ErrorNote, Hint, Panel } from "@/components/ci";
import { CompetitorAvatar } from "@/components/CompetitorAvatar";
import { useRecord } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { STATE_INFO, STATE_ORDER, anyMark, buildMatrix, type DataState, type MatrixCell } from "@/lib/matrix";
import { Check, Clock, HelpCircle, Minus } from "lucide-react";
import { useMeta } from "@/lib/meta";
import type { CompetitorProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICON = { check: Check, clock: Clock, question: HelpCircle, dash: Minus } as const;

/** The state's icon in its colour: icon and colour always together, with the state's name for screen readers. */
export function StateIcon({ state }: { state: DataState }) {
  const s = STATE_INFO[state];
  const Icon = ICON[s.icon];
  return (
    <span role="img" aria-label={s.label} data-state={state}
      className="inline-flex size-4 shrink-0 items-center justify-center rounded-full" style={{ background: s.fg, color: "#fff" }}>
      <Icon className="size-3" strokeWidth={3} aria-hidden />
    </span>
  );
}

function host(url: string): string {
  try { return new URL(url).host.replace(/^www\./, ""); } catch { return url; }
}

const ChangedMark = ({ text }: { text: string }) => <span className="rounded-[3px] border border-[#f59e0b] px-1 text-[10px] text-[#8a5a00]">{text}</span>;
const ReviewMark = () => <span className="rounded-[3px] border border-line px-1 text-[10px] text-mute">needs review</span>;

function CellHint({ c, who, axis }: { c: MatrixCell; who: string; axis: string }) {
  return (
    <span className="flex flex-col gap-1">
      <b className="font-semibold">{who} · {axis}: {STATE_INFO[c.state].label}</b>
      {c.full ? <span>{c.full}</span> : c.why ? <span>{c.why}</span> : null}
      {c.source ? <span>Source: {host(c.source)}{c.asOf ? ` · as of ${fmtDate(c.asOf, true)}` : ""}</span> : c.asOf ? <span>As of {fmtDate(c.asOf, true)}</span> : null}
      {c.stale && c.staleReason ? <span>Stale: {c.staleReason}</span> : null}
      {c.needsReview ? <span>Needs review</span> : null}
      {c.changedAt ? <span>Changed {fmtDate(c.changedAt, true)}, found by change detection</span> : null}
    </span>
  );
}

function MatrixTd({ c, who, axis }: { c: MatrixCell; who: string; axis: string }) {
  const st = STATE_INFO[c.state];
  return (
    <td className="min-w-[9rem] max-w-[12rem] border-b border-l border-line px-2 py-2 align-top text-xs"
      style={{ background: st.bg }} data-cell={c.state}>
      <span className="flex items-start gap-1.5">
        <StateIcon state={c.state} />
        <Hint text={<CellHint c={c} who={who} axis={axis} />} className="min-w-0 flex-1">
          <span className={cn(!c.full && "italic")} style={{ color: c.full ? undefined : st.fg }}>{c.short}</span>
        </Hint>
      </span>
      {c.source || c.changedAt || c.needsReview ? (
        <span className="mt-1 flex flex-wrap items-center gap-1">
          {c.source ? <ArticleLink href={c.source} label={`Open the source page for ${who}, ${axis}, in a new tab`} /> : null}
          {c.changedAt ? <ChangedMark text={`changed ${fmtDate(c.changedAt)}`} /> : null}
          {c.needsReview ? <ReviewMark /> : null}
        </span>
      ) : null}
    </td>
  );
}

export const CAPTION = "Colour shows what we found on each competitor's public pages, not a verdict on their product.";

/** Six profile calls (the same ones the profile pages make); the matrix waits for all, a failed one says so. */
export function CapabilityMatrix() {
  const { data: meta } = useMeta();
  const keys = (meta?.competitors ?? []).filter((c) => !c.is_industry && c.key !== "industry").map((c) => c.key).slice(0, 6);
  const q = [0, 1, 2, 3, 4, 5].map((i) => useRecord<CompetitorProfile>(keys[i] ? `/api/v1/competitors/${encodeURIComponent(keys[i])}` : null, keys[i], (d) => d.key)); // eslint-disable-line react-hooks/rules-of-hooks
  const loading = !meta || q.slice(0, keys.length).some((x) => !x.data && !x.error);
  const errors = q.filter((x) => x.error);
  const profiles = keys.map((k, i) => ({ key: k, name: q[i].data?.name ?? k, axes: q[i].data?.head_to_head?.axes }));
  const rows = buildMatrix(profiles);
  const marks = { changed: anyMark(rows, "changedAt"), review: anyMark(rows, "needsReview") };
  return (
    <Panel title="JFrog vs competitors">
      <p className="m-0 mb-2 text-xs text-[#44516a]" data-caption>{CAPTION}</p>
      {errors.length ? <div className="mb-2"><ErrorNote error={errors[0].error!} onRetry={() => errors.forEach((x) => x.mutate())} /></div> : null}
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-mute" data-legend aria-label="Legend">
        {STATE_ORDER.map((k) => (
          <span key={k} className="inline-flex items-center gap-1 rounded px-1.5 py-0.5" style={{ background: STATE_INFO[k].bg }}>
            <StateIcon state={k} /><span style={{ color: STATE_INFO[k].fg }} className="font-semibold">{STATE_INFO[k].label}</span>
          </span>
        ))}
        {marks.changed ? <span className="inline-flex items-center gap-1"><ChangedMark text="changed + date" />: found by change detection on that date</span> : null}
        {marks.review ? <span className="inline-flex items-center gap-1"><ReviewMark />: an analyst should confirm this value</span> : null}
        <span>Hover or focus a cell for its full text, source and date</span>
      </div>
      {loading ? <div className="py-4 text-xs text-mute" role="status">Loading the head-to-head data…</div> : (
        <div className="overflow-x-auto" data-matrix>
          <table className="w-full min-w-[64rem] border-collapse">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 border-b border-line bg-card px-2 py-2 text-left text-xs font-semibold text-mute">Capability</th>
                <th className="border-b border-l border-line px-2 py-2 text-left text-xs font-semibold">JFrog</th>
                {profiles.map((p) => (
                  <th key={p.key} className="border-b border-l border-line px-2 py-2 text-left text-xs font-semibold">
                    <span className="inline-flex items-center gap-1.5"><CompetitorAvatar k={p.key} name={p.name} size="md" />{p.name}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.axis}>
                  <th scope="row" className="sticky left-0 z-10 w-[9rem] border-b border-line bg-card px-2 py-2 text-left align-top text-xs font-semibold">{r.label}</th>
                  <MatrixTd c={r.jfrog} who="JFrog" axis={r.label} />
                  {profiles.map((p) => <MatrixTd key={p.key} c={r.cells[p.key]} who={p.name} axis={r.label} />)}
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length ? <div className="py-3 text-xs text-mute">No head-to-head data yet.</div> : null}
        </div>
      )}
    </Panel>
  );
}
