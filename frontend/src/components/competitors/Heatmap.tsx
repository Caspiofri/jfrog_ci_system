"use client";
// "Where competitors are active": items per competitor and category in the last 7 days by feed date. Counted from
// Log rows; click a cell to list its items (the title opens the drawer).
import { useState } from "react";
import useSWR from "swr";
import { Empty, ErrorNote, ItemTitle, Panel, ScoreBadge } from "@/components/ci";
import { CompetitorAvatar } from "@/components/CompetitorAvatar";
import { useItemDrawer } from "@/components/ItemDrawer";
import { ApiError, get, path } from "@/lib/api";
import { CATEGORY_COLOR, fmtDate } from "@/lib/format";
import { ZERO_BG, buildHeatmap, heatColor, heatmapQuery, legendSteps } from "@/lib/heatmap";
import { useMeta } from "@/lib/meta";
import { remainingOffsets } from "@/lib/reviewQueue";
import type { Log, LogRow } from "@/lib/types";
import { cn } from "@/lib/utils";

export const HEATMAP_CAPTION = "Activity by category, from automatic classification. Last 7 days.";
const RING_NOTE = "Ring = this competitor's most active category";

async function getAllRows(url: string): Promise<{ rows: LogRow[]; now: string }> {
  const first = await get<Log>(url);
  const rest = remainingOffsets(first.total, first.items.length);
  const pages = await Promise.all(rest.map((o) => get<Log>(url.replace(/([?&])offset=0\b/, `$1offset=${o}`))));
  return { rows: [...first.items, ...pages.flatMap((p) => p.items)], now: first.meta.now };
}

export function ActivityHeatmap() {
  const { data: meta } = useMeta();
  const drawer = useItemDrawer();
  const [sel, setSel] = useState<{ c: string; k: string } | null>(null);
  const comps = (meta?.competitors ?? []).filter((c) => !c.is_industry && c.key !== "industry").slice(0, 6);
  const keys = comps.map((c) => c.key);
  const now = meta?.meta?.now;
  const q = useSWR<{ rows: LogRow[]; now: string }, ApiError>(
    now && keys.length ? path("/log", heatmapQuery(keys, now)) : null, getAllRows, { revalidateOnFocus: false });
  const cats = Object.keys(CATEGORY_COLOR);
  const hm = q.data ? buildHeatmap(q.data.rows, keys, cats, now ?? q.data.now) : null;
  const name = (k: string) => comps.find((c) => c.key === k)?.name ?? k;
  const picked = hm && sel ? hm.cells[sel.c]?.[sel.k] : null;
  return (
    <Panel title="Where competitors are active">
      <p className="m-0 mb-2 text-xs text-[#44516a]" data-caption>{HEATMAP_CAPTION}</p>
      {q.error ? <ErrorNote error={q.error} onRetry={() => q.mutate()} /> : null}
      {!hm ? (q.error ? null : <div className="py-4 text-xs text-mute" role="status">Counting the last 7 days…</div>) : !hm.total ? (
        <Empty>No items from the tracked competitors were published in the last 7 days.</Empty>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-mute" data-legend aria-label="Legend">
            <span className="font-semibold">Items:</span>
            <span className="inline-flex items-center gap-1"><i className="inline-block size-3 rounded-sm ring-1 ring-black/10" style={{ background: ZERO_BG }} aria-hidden />0</span>
            {legendSteps(hm.max).map((n) => (
              <span key={n} className="inline-flex items-center gap-1"><i className="inline-block size-3 rounded-sm" style={{ background: heatColor(n, hm.max).bg }} aria-hidden />{n}</span>
            ))}
            <span className="inline-flex items-center gap-1"><i className="inline-block size-3 rounded-full ring-2 ring-[#f59e0b]" aria-hidden />{RING_NOTE}</span>
            <span>Feed dates {fmtDate(hm.from)}–{fmtDate(hm.to)} · {hm.total} items · not noise, not dismissed</span>
          </div>
          <div className="overflow-x-auto" data-heatmap>
            <table className="w-full min-w-[44rem] border-collapse">
              <thead>
                <tr>
                  <th className="sticky left-0 z-10 border-b border-line bg-card px-2 py-2 text-left text-xs font-semibold text-mute">Category</th>
                  {keys.map((k) => (
                    <th key={k} className="border-b border-l border-line px-2 py-2 text-center text-xs font-semibold">
                      <span className="inline-flex items-center gap-1.5"><CompetitorAvatar k={k} name={name(k)} size="md" />{name(k)}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cats.map((cat) => (
                  <tr key={cat}>
                    <th scope="row" className="sticky left-0 z-10 w-[11rem] border-b border-line bg-card px-2 py-1.5 text-left text-xs font-semibold">{cat}</th>
                    {keys.map((k) => {
                      const cell = hm.cells[k][cat];
                      const col = heatColor(cell.count, hm.max);
                      const on = sel?.c === k && sel?.k === cat;
                      return (
                        <td key={k} className="border-b border-l border-line p-1 text-center" data-count={cell.count} data-ring={cell.ring ? "1" : undefined}>
                          <button type="button" disabled={!cell.count} onClick={() => setSel(on ? null : { c: k, k: cat })}
                            aria-label={`${name(k)}, ${cat}: ${cell.count} items${cell.ring ? ", most active category" : ""}`} aria-pressed={on}
                            className={cn("mx-auto flex h-8 w-full min-w-[3.5rem] items-center justify-center rounded text-sm font-semibold tabular-nums",
                              cell.count ? "cursor-pointer hover:outline hover:outline-2 hover:outline-jgreen" : "cursor-default", on && "outline outline-2 outline-jgreen")}
                            style={{ background: col.bg, color: col.fg }}>
                            <span className={cn("inline-flex size-7 items-center justify-center rounded-full", cell.ring && "ring-2 ring-[#f59e0b]")}>{cell.count}</span>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {picked && sel ? (
            <div className="mt-3 rounded border border-line px-3 py-2" data-heat-items>
              <div className="mb-1 flex items-center gap-2 text-xs font-semibold">
                <CompetitorAvatar k={sel.c} name={name(sel.c)} /> {name(sel.c)} · {sel.k} · {picked.count} {picked.count === 1 ? "item" : "items"}
                <button type="button" className="ml-auto text-mute hover:text-jgreen-d" onClick={() => setSel(null)}>Close</button>
              </div>
              {picked.items.map((r) => (
                <div key={r.item_id} className="flex items-start gap-2 border-t border-line py-1.5 text-xs first:border-t-0">
                  <ScoreBadge score={r.score} />
                  <span className="min-w-0 flex-1"><ItemTitle title={r.title} url={r.url} onOpen={() => drawer.open(r.item_id!)} /></span>
                  <span className="shrink-0 text-mute">{fmtDate(r.published_at)}</span>
                </div>
              ))}
            </div>
          ) : null}
        </>
      )}
    </Panel>
  );
}
