"use client";
// "Is this day unusual?": sum of scores of published items per discovery day (contract §4.8). One series, one hue.
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtDate } from "@/lib/format";

type Row = { date: string; score: number; items: number };

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded border border-line bg-white px-2 py-1 text-xs shadow-md">
      <div className="font-semibold">{fmtDate(r.date, true)}</div>
      <div>Importance sum {r.score}</div>
      <div className="text-mute">{r.items} published items</div>
    </div>
  );
}

export function IntensityChart({ series, current }: { series: Row[]; current: string }) {
  return (
    <div className="h-[170px] w-full" role="img" aria-label="Importance sum per discovery day">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={series} margin={{ top: 6, right: 4, bottom: 0, left: -18 }} barCategoryGap={3}>
          <CartesianGrid vertical={false} stroke="#eaeef4" />
          <XAxis dataKey="date" tickFormatter={(d: string) => fmtDate(d)} tick={{ fontSize: 11, fill: "#6b7788" }} tickLine={false} axisLine={{ stroke: "#e3e8ef" }} interval="preserveStartEnd" minTickGap={18} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#6b7788" }} tickLine={false} axisLine={false} />
          <Tooltip content={<Tip />} cursor={{ fill: "#f4f6f9" }} />
          <Bar dataKey="score" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false}>
            {series.map((r) => (
              <Cell key={r.date} fill={r.date === current ? "#2e9b44" : "#3f5b8f"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
