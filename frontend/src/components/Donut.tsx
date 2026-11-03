"use client";
// The prototype's donut + legend, in Recharts. Legend always shown with counts, so color is never the only cue.
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

export type Part = { label: string; value: number; color: string };

export function Donut({ parts, center, caption }: { parts: Part[]; center: string | number; caption?: string }) {
  const data = parts.filter((p) => p.value > 0);
  return (
    <div className="flex flex-wrap items-center gap-[1.125rem]">
      <div className="relative size-[9.375rem] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data.length ? data : [{ label: "", value: 1, color: "#eaeef4" }]} dataKey="value" nameKey="label"
              innerRadius={48} outerRadius={72} paddingAngle={data.length > 1 ? 1.5 : 0} stroke="#fff" strokeWidth={2} isAnimationActive={false}>
              {(data.length ? data : [{ color: "#eaeef4" }]).map((p, i) => <Cell key={i} fill={p.color} />)}
            </Pie>
            {data.length ? <Tooltip formatter={(v: number, n: string) => [v, n]} /> : null}
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold tabular-nums">{center}</span>
          {caption ? <span className="text-[0.6875rem] text-mute">{caption}</span> : null}
        </div>
      </div>
      <div className="min-w-[9rem] flex-1">
        {parts.map((p) => (
          <div key={p.label} className="grid grid-cols-[0.75rem_1fr_auto] items-center gap-2 py-[3px]">
            <i className="size-2.5 rounded-sm" style={{ background: p.color }} />
            <span>{p.label}</span>
            <b className="font-semibold tabular-nums">{p.value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}
