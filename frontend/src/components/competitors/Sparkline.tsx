"use client";
// D93/D94: "Cleared Items per Day · Last 14 Days" inside each competitor card, from the profile's activity series.
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useRecord } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { SPARK_CAPTION, SPARK_TITLE, lastDays, type DayRow } from "@/lib/sparkline";
import type { CompetitorProfile } from "@/lib/types";

function Tip({ active, payload }: { active?: boolean; payload?: { payload: DayRow }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded border border-line bg-white px-2 py-1 text-[0.6875rem] shadow-sm" data-spark-tip>
      {fmtDate(r.date, true)} · {r.items} cleared {r.items === 1 ? "item" : "items"}
    </div>
  );
}

export function CardSparkline({ k }: { k: string }) {
  // the same SWR key as the matrix and the profile, so no extra request where they already loaded it
  const q = useRecord<CompetitorProfile>(`/api/v1/competitors/${encodeURIComponent(k)}`, k, (d) => d.key);
  const a = q.data?.activity;
  const rows = a && q.data?.date ? lastDays(a.series, q.data.date) : null;
  return (
    <div className="flex flex-col gap-0.5" data-sparkline={k}>
      <span className="text-[0.6875rem] font-semibold text-ink">{SPARK_TITLE}</span>
      {rows ? (
        <div className="h-10 w-full" role="img" aria-label={`${SPARK_TITLE}: ${rows.map((r) => `${fmtDate(r.date)} ${r.items}`).join(", ")}`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 3, right: 3, bottom: 3, left: 3 }}>
              <XAxis dataKey="date" hide />
              <YAxis hide domain={[0, "dataMax"]} />
              <Tooltip content={<Tip />} cursor={{ stroke: "#cbd3df" }} />
              <Line type="monotone" dataKey="items" stroke="#3f5b8f" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-10 w-full" role="status" aria-label="Loading" />
      )}
      <span className="text-[0.625rem] text-mute">{SPARK_CAPTION}</span>
    </div>
  );
}
