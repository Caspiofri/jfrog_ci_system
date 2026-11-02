"use client";
// "JFrog vs competitors": every capability row, JFrog first, then the six tracked competitors. Values as the
// head-to-head data holds them; no comparison, no verdict (the analyst draws the conclusion).
import { ArticleLink, ErrorNote, Hint, Panel } from "@/components/ci";
import { CompetitorAvatar } from "@/components/CompetitorAvatar";
import { useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { NOT_FOUND, anyMark, buildMatrix, type MatrixCell } from "@/lib/matrix";
import { useMeta } from "@/lib/meta";
import type { CompetitorProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

const STALE_BG = "#fff4e0";
const CHANGED_BG = "#fff7e6";

function host(url: string): string {
  try { return new URL(url).host.replace(/^www\./, ""); } catch { return url; }
}

const ChangedMark = ({ text }: { text: string }) => <span className="rounded-[3px] border border-[#f59e0b] px-1 text-[10px] text-[#8a5a00]">{text}</span>;
const StaleMark = () => <span className="rounded-[3px] bg-[#fff4e0] px-1 text-[10px] text-[#8a5a00] ring-1 ring-[#f59e0b]/40">stale</span>;
const ReviewMark = () => <span className="rounded-[3px] border border-line px-1 text-[10px] text-mute">needs review</span>;

function CellHint({ c, who, axis }: { c: MatrixCell; who: string; axis: string }) {
  return (
    <span className="flex flex-col gap-1">
      <b className="font-semibold">{who} · {axis}</b>
      <span>{c.full ?? `${NOT_FOUND}. ${c.why ?? ""}`}</span>
      {c.source ? <span>Source: {host(c.source)}{c.asOf ? ` · as of ${fmtDate(c.asOf, true)}` : ""}</span> : c.asOf ? <span>As of {fmtDate(c.asOf, true)}</span> : null}
      {c.stale ? <span>Stale{c.staleReason ? `: ${c.staleReason}` : ""}</span> : null}
      {c.needsReview ? <span>Needs review</span> : null}
      {c.changedAt ? <span>Changed {fmtDate(c.changedAt, true)}, found by change detection</span> : null}
    </span>
  );
}

function MatrixTd({ c, who, axis, jfrog = false }: { c: MatrixCell; who: string; axis: string; jfrog?: boolean }) {
  return (
    <td className={cn("min-w-[11rem] max-w-[15rem] border-b border-l border-line px-2 py-2 align-top text-xs", jfrog && "bg-[#f8fbf8]")}
      style={c.changedAt ? { background: CHANGED_BG } : c.stale ? { background: STALE_BG } : undefined}
      data-cell={c.empty ? "empty" : "value"}>
      <span className="flex items-start gap-1">
        <Hint text={<CellHint c={c} who={who} axis={axis} />} className="min-w-0 flex-1">
          <span className={cn(c.empty && "italic text-mute")}>{c.text}</span>
        </Hint>
        {c.source ? <ArticleLink href={c.source} label={`Open the source page for ${who}, ${axis}, in a new tab`} /> : null}
      </span>
      {c.changedAt || c.stale || c.needsReview ? (
        <span className="mt-1 flex flex-wrap gap-1 text-[10px]">
          {c.changedAt ? <ChangedMark text={`changed ${fmtDate(c.changedAt)}`} /> : null}
          {c.stale ? <StaleMark /> : null}
          {c.needsReview ? <ReviewMark /> : null}
        </span>
      ) : null}
    </td>
  );
}

/** Six profile calls (the same ones the profile pages make); the matrix waits for all, a failed one says so. */
export function CapabilityMatrix() {
  const { data: meta } = useMeta();
  const keys = (meta?.competitors ?? []).filter((c) => !c.is_industry && c.key !== "industry").map((c) => c.key).slice(0, 6);
  const q = [0, 1, 2, 3, 4, 5].map((i) => useApi<CompetitorProfile>(keys[i] ? `/api/v1/competitors/${encodeURIComponent(keys[i])}` : null)); // eslint-disable-line react-hooks/rules-of-hooks
  const loading = !meta || q.slice(0, keys.length).some((x) => !x.data && !x.error);
  const errors = q.filter((x) => x.error);
  const profiles = keys.map((k, i) => ({ key: k, name: q[i].data?.name ?? k, axes: q[i].data?.head_to_head?.axes }));
  const rows = buildMatrix(profiles);
  const marks = { changed: anyMark(rows, "changedAt"), stale: anyMark(rows, "stale"), review: anyMark(rows, "needsReview") };
  return (
    <Panel title="JFrog vs competitors" cap="Capabilities from public sources, with source and date for every cell.">
      {errors.length ? <div className="mb-2"><ErrorNote error={errors[0].error!} onRetry={() => errors.forEach((x) => x.mutate())} /></div> : null}
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-mute" data-legend aria-label="Legend">
        <span className="inline-flex items-center gap-1"><i className="inline-block size-2.5 rounded-sm bg-[#f8fbf8] ring-1 ring-black/10" aria-hidden />JFrog column</span>
        <span><i className="italic">{NOT_FOUND}</i>: no value in the public sources we track</span>
        {marks.stale ? <span className="inline-flex items-center gap-1"><i className="inline-block size-2.5 rounded-sm ring-1 ring-black/10" style={{ background: STALE_BG }} aria-hidden /><StaleMark />: the source page could not be re-checked</span> : null}
        {marks.changed ? <span className="inline-flex items-center gap-1"><i className="inline-block size-2.5 rounded-sm ring-1 ring-black/10" style={{ background: CHANGED_BG }} aria-hidden /><ChangedMark text="changed + date" />: found by change detection on that date</span> : null}
        {marks.review ? <span className="inline-flex items-center gap-1"><ReviewMark />: an analyst should confirm this value</span> : null}
        <span>Source opens the page a value came from · hover or focus a cell for its full text, source and date</span>
      </div>
      {loading ? <div className="py-4 text-xs text-mute" role="status">Loading the head-to-head data…</div> : (
        <div className="overflow-x-auto" data-matrix>
          <table className="w-full min-w-[64rem] border-collapse">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 border-b border-line bg-card px-2 py-2 text-left text-xs font-semibold text-mute">Capability</th>
                <th className="border-b border-l border-line bg-[#f8fbf8] px-2 py-2 text-left text-xs font-semibold">JFrog</th>
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
                  <MatrixTd c={r.jfrog} who="JFrog" axis={r.label} jfrog />
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
