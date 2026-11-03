"use client";
// "How do they compare with JFrog?": every axis, the competitor's cell beside JFrog's (D20). Cell states from §9.
import { Fragment, useState } from "react";
import Link from "next/link";
import { History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ArticleLink, Async, ColorLegend, Tag, UnverifiedNote } from "@/components/ci";
import { path, useRecord } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { displayValue } from "@/lib/matrix";
import type { Cell, CellHistoryRow, H2HAxis, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

function CellView({ c, axis }: { c: Cell; axis: string }) {
  if (c.state === "not_tracked") {
    return <span className="italic text-mute" title={c.reason}>Not tracked{c.reason ? `: ${c.reason}` : ""}</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      {c.state === "not_stated" ? (
        <span className="italic text-mute" title="The page says nothing on this axis: a gap in what we know, not a value">Not stated on the page</span>
      ) : (
        <span>{displayValue(axis, c.value)}</span>
      )}
      <span className="flex flex-wrap items-center gap-1.5 text-[0.6875rem] text-mute">
        {c.state === "stale" ? <Tag className="bg-[#fff4e0] text-[#8a5a00]" title={c.stale_reason}>Stale{c.stale_reason ? `: ${c.stale_reason}` : ""}</Tag> : null}
        {c.needs_review ? <Tag className="bg-[#fffaf0] text-[#8a5a00]" title={c.review_reason}>Needs review</Tag> : null}
        {c.source_url ? <ArticleLink href={c.source_url} label="Open the source page in a new tab" /> : null}
        {c.as_of ? <span>as of {fmtDate(c.as_of, true)}</span> : null}
        {c.note ? <span>· {c.note}</span> : null}
      </span>
      {c.change ? (
        <div className="rounded border border-[#f59e0b] bg-[#fff7e6] px-2 py-1 text-xs">
          <b className="font-semibold">Changed {fmtDate(c.change.detected_at)}</b>
          {c.change.status === "awaiting_review" ? (
            <> · <Link href="/review?reason=changed_cell" className="text-jgreen-d hover:underline">awaiting review</Link></>
          ) : <span className="text-mute"> · {c.change.status.replace(/_/g, " ")}</span>}
          <div className="text-mute">Was: {displayValue(axis, c.change.old_value) || "—"}</div>
        </div>
      ) : null}
    </div>
  );
}

function HistoryRows({ who, axis, name }: { who: string; axis: string; name: string }) {
  const q = useRecord<Page<CellHistoryRow> & { competitor: string; axis: string }>(
    path(`/competitors/${encodeURIComponent(who)}/cells/${encodeURIComponent(axis)}/history`), `${who}/${axis}`, (d) => `${d.competitor}/${d.axis}`);
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-mute">{name}</div>
      <Async {...q} retry={() => q.mutate()} rows={2} isEmpty={(d) => !d.items.length} empty="No history.">
        {(d) => d.items.map((h, i) => (
          <div key={i} className="border-t border-line py-1 text-xs first:border-t-0">
            <span className="text-mute">{fmtDate(h.as_of, true)} · {h.event}</span>
            <div>{displayValue(axis, h.value) || <i className="text-mute">empty</i>}</div>
          </div>
        ))}
      </Async>
    </div>
  );
}

export function HeadToHead({ competitor, name, axes }: { competitor: string; name: string; axes: H2HAxis[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const td = "border-b border-line px-2.5 py-2.5 align-top";
  return (
    <div className="overflow-x-auto">
      <UnverifiedNote className="mb-3" />
      <table className="w-full min-w-[45rem] border-collapse">
        <thead>
          <tr>
            {["Axis", "JFrog", name, ""].map((h, i) => (
              <th key={i} className="border-b border-line px-2.5 py-2 text-left text-xs font-semibold text-mute">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {axes.map((a) => (
            <Fragment key={a.axis}>
              <tr className={cn(a.changed && "bg-[#fff7e6]")}>
                <td className={`${td} w-[9rem] font-semibold`}>
                  {a.label}
                  {a.changed ? <div className="text-[0.6875rem] font-normal text-[#8a5a00]">changed this week</div> : null}
                </td>
                <td className={`${td} w-[40%]`}><CellView c={a.jfrog} axis={a.axis} /></td>
                <td className={`${td} w-[40%]`}><CellView c={a.competitor} axis={a.axis} /></td>
                <td className={`${td} w-[5rem]`}>
                  <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" aria-expanded={open === a.axis}
                    onClick={() => setOpen(open === a.axis ? null : a.axis)}>
                    <History className="size-3.5" /> History
                  </Button>
                </td>
              </tr>
              {open === a.axis ? (
                <tr>
                  <td className={td} />
                  <td className={td}><HistoryRows who="jfrog" axis={a.axis} name="JFrog" /></td>
                  <td className={td}><HistoryRows who={competitor} axis={a.axis} name={name} /></td>
                  <td className={td} />
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
      {axes.some((a) => a.changed) ? (
        <ColorLegend className="mt-2" items={[{ color: "#fff7e6", label: "Highlighted row: changed this week, goes to review" }]} />
      ) : null}
    </div>
  );
}
