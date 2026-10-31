"use client";
// "How active are they?": published items per publication day, 30 days. Days with an item rated 4 or 5 are red.
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtDate } from "@/lib/format";

type Row = { date: string; items: number; max_score: number | null };
const HOT = "#e5483b";
const BASE = "#3f5b8f";

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded border border-line bg-white px-2 py-1 text-xs shadow-md">
      <div className="font-semibold">{fmtDate(r.date, true)}</div>
      <div>{r.items} published items</div>
      {r.max_score ? <div className="text-mute">top importance {r.max_score}</div> : null}
    </div>
  );
}

export function ActivityChart({ series }: { series: Row[] }) {
  return (
    <div>
      <div className="h-[190px] w-full" role="img" aria-label="Published items per publication day, 30 days">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={series} margin={{ top: 6, right: 4, bottom: 0, left: -18 }} barCategoryGap={2}>
            <CartesianGrid vertical={false} stroke="#eaeef4" />
            <XAxis dataKey="date" tickFormatter={(d: string) => fmtDate(d)} tick={{ fontSize: 11, fill: "#6b7788" }} tickLine={false} axisLine={{ stroke: "#e3e8ef" }} interval="preserveStartEnd" minTickGap={24} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#6b7788" }} tickLine={false} axisLine={false} />
            <Tooltip content={<Tip />} cursor={{ fill: "#f4f6f9" }} />
            <Bar dataKey="items" radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={false}>
              {series.map((r) => <Cell key={r.date} fill={(r.max_score ?? 0) >= 4 ? HOT : BASE} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1.5 flex gap-4 text-[11px] text-mute">
        <span className="inline-flex items-center gap-1"><i className="inline-block size-2 rounded-sm" style={{ background: BASE }} /> items per day</span>
        <span className="inline-flex items-center gap-1"><i className="inline-block size-2 rounded-sm" style={{ background: HOT }} /> a day with an item rated 4 or 5</span>
      </div>
    </div>
  );
}
