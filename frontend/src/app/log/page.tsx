"use client";
// Log: layout and titles kept from the prototype (the user liked it as is). Data from GET /api/v1/log.
import { CompetitorLabel } from "@/components/CompetitorAvatar";
import { Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Async, ColourLegends, Empty, HBars, ItemTitle, Loading, PageHead, Panel, ScoreBadge, StatusDot } from "@/components/ci";
import { Donut } from "@/components/Donut";
import { FilterSelect } from "@/components/FilterSelect";
import { useItemDrawer } from "@/components/ItemDrawer";
import { ReopenButton } from "@/components/review/actions";
import { path, useApi } from "@/lib/api";
import { competitorFilterOptions } from "@/lib/competitorLabel";
import { DISMISS_LABEL, STAGE_LABEL, STATUS_COLOR, STATUS_LABEL, fmtDate, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import { useUrlState } from "@/lib/useParams";
import type { Log, LogRow } from "@/lib/types";

const PAGE = 100;
const STATUS_ORDER = ["auto_published", "awaiting_review", "approved", "flagged", "dismissed", "dropped", "held_out", "unclassified"];

export default function LogPage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <LogScreen />
    </Suspense>
  );
}

function LogScreen() {
  const { get, set } = useUrlState();
  const { data: meta } = useMeta();
  const competitor = get("competitor");
  const category = get("category");
  const status = get("status");
  const date = get("date");
  const offset = Number(get("offset") || 0);
  // Counts ignore the status filter (as the API computes them), so the donut stays whole while the table narrows.
  const q = useApi<Log>(path("/log", { competitor, category, status, date_from: date, date_to: date, limit: PAGE, offset }));
  const filtered = Boolean(competitor || category || status || date);

  return (
    <>
      <PageHead title="Log" info="Every collected item, including dropped ones." />
      <Async {...q} retry={() => q.mutate()} rows={6}>
        {(d) => {
          const byStatus = d.counts.status;
          const collected = Object.values(byStatus).reduce((a, b) => a + b, 0);
          return (
            <>
              <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))]">
                <Panel title="By status">
                  <Donut center={collected} caption="collected" parts={STATUS_ORDER.filter((k) => byStatus[k]).map((k) => ({
                    label: label(STATUS_LABEL, k), value: byStatus[k], color: STATUS_COLOR[k] ?? "#cbd3df",
                  }))} />
                </Panel>
                <Panel title="Where items stopped">
                  {Object.keys(d.counts.stage).length ? (
                    <HBars rows={Object.entries(d.counts.stage).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: label(STAGE_LABEL, k), value: v }))} />
                  ) : <Empty>No items.</Empty>}
                </Panel>
              </div>

              <ColourLegends unscored />

              <Panel>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <FilterSelect ariaLabel="Competitor" allLabel="All competitors" value={competitor} onChange={(v) => set({ competitor: v, offset: null })}
                    options={competitorFilterOptions(meta)} />
                  <FilterSelect ariaLabel="Category" allLabel="All categories" value={category} onChange={(v) => set({ category: v, offset: null })}
                    options={(meta?.categories ?? []).map((c) => ({ value: c, label: c }))} />
                  <FilterSelect ariaLabel="Status" allLabel="All statuses" value={status} onChange={(v) => set({ status: v, offset: null })}
                    options={(meta?.statuses ?? STATUS_ORDER).map((s) => ({ value: s, label: label(STATUS_LABEL, s) }))} />
                  <input type="date" aria-label="Date" min="2000-01-01" max="2099-12-31" value={date}
                    onChange={(e) => e.target.validity.valid && set({ date: e.target.value || null, offset: null })}
                    className="h-8 rounded border border-input bg-white px-2.5 text-[13px]" />
                  <Button variant="outline" size="sm" className="h-8 text-xs" disabled={!filtered}
                    onClick={() => set({ competitor: null, category: null, status: null, date: null, offset: null })}>Reset</Button>
                  <span className="text-xs text-mute">{d.total} of {collected} items</span>
                </div>
                {d.items.length ? (
                  <div className="max-h-[30rem] overflow-auto">
                    <table className="w-full border-collapse">
                      <thead>
                        <tr>
                          {["Date", "Competitor", "Title", "Category", "Score", "Status", "Stopped at", "Reason"].map((h) => (
                            <th key={h} className="sticky top-0 z-10 border-b border-line bg-white px-2.5 py-2 text-left text-xs font-semibold text-mute">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {d.items.map((r, i) => <LogTr key={`${r.item_id}-${r.run_id}-${r.stage}-${i}`} r={r} />)}
                      </tbody>
                    </table>
                  </div>
                ) : <Empty>Nothing matches these filters.</Empty>}
                {d.total > PAGE ? (
                  <div className="mt-2.5 flex items-center justify-end gap-2">
                    <span className="text-xs text-mute">{offset + 1}–{Math.min(offset + PAGE, d.total)} of {d.total}</span>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset === 0} onClick={() => set({ offset: String(Math.max(0, offset - PAGE)) })}>Previous</Button>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset + PAGE >= d.total} onClick={() => set({ offset: String(offset + PAGE) })}>Next</Button>
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

function LogTr({ r }: { r: LogRow }) {
  const drawer = useItemDrawer();
  const dropped = r.status === "dropped";
  const td = "border-b border-line px-2.5 py-[9px] align-top";
  return (
    <tr>
      <td className={`${td} whitespace-nowrap`}>{fmtDate(r.collected_at)}</td>
      <td className={`${td} whitespace-nowrap`}>{r.competitor ? <CompetitorLabel k={r.competitor} /> : "—"}</td>
      <td className={td}>
        <ItemTitle title={r.title} url={r.url} onOpen={dropped || !r.item_id ? undefined : () => drawer.open(r.item_id!)} />
        {dropped && r.duplicate_of ? (
          <button type="button" className="ml-1 text-xs text-mute hover:text-jgreen-d" onClick={() => drawer.open(r.duplicate_of!)}>· kept item</button>
        ) : null}
      </td>
      <td className={td}>{r.category ?? "—"}</td>
      <td className={td}><ScoreBadge score={r.score} noise={r.stage === "classify" && r.score === null} /></td>
      <td className={td}><StatusDot status={r.status} /></td>
      <td className={`${td} whitespace-nowrap`}>{label(STAGE_LABEL, r.stage)}</td>
      <td className={`${td} text-mute`}>
        {r.dismiss_reason ? `Dismissed: ${label(DISMISS_LABEL, r.dismiss_reason)}` : r.reason || "—"}
        {r.status === "dismissed" && r.item_id ? <div className="mt-1"><ReopenButton itemId={r.item_id} title={r.title} /></div> : null}
      </td>
    </tr>
  );
}
