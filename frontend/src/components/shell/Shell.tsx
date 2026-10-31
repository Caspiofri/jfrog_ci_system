"use client";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Activity, BarChart3, CheckCircle2, FileText, List, Map } from "lucide-react";
import { ItemDrawerProvider } from "@/components/ItemDrawer";
import { useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { runTime, useMeta } from "@/lib/meta";
import type { Review } from "@/lib/types";
import { cn } from "@/lib/utils";

const NAV: { group: string; items: { href: string; label: string; icon: typeof FileText; badge?: "review" }[] }[] = [
  { group: "Primary", items: [
    { href: "/brief", label: "Daily Brief", icon: FileText },
    { href: "/competitors", label: "Competitors", icon: BarChart3 },
  ] },
  { group: "Supporting", items: [
    { href: "/review", label: "Review queue", icon: CheckCircle2, badge: "review" },
    { href: "/log", label: "Log", icon: List },
    { href: "/health", label: "Health", icon: Activity },
  ] },
  { group: "Later", items: [{ href: "/roadmap", label: "Roadmap", icon: Map }] },
];

function RunPill() {
  const { data, error } = useMeta();
  if (error) return <span className="rounded border border-[#d14343] px-2.5 py-1 text-xs text-[#ff8a8a]">API unreachable</span>;
  if (!data) return null;
  const t = runTime(data.latest_run_id);
  return (
    <span className="flex items-center gap-2">
      {data.meta.mode === "demo" ? <span className="rounded bg-[#f59e0b] px-2 py-0.5 text-xs font-semibold text-navy">Demo snapshot</span> : null}
      <span className="rounded border border-jgreen px-2.5 py-1 text-xs text-jgreen" title={data.latest_run_id ?? undefined}>
        {t ? `Latest run ${fmtDateTime(t)} Israel time` : "No run yet"}
      </span>
    </span>
  );
}

function ReviewCount() {
  const { data } = useApi<Review>("/api/v1/review?limit=1");
  const n = data?.backlog_total ?? data?.total; // §10.3: the unfiltered backlog
  if (!n) return null;
  // The whole backlog (every undecided held item), not one Brief's window: say so, so it isn't read as today's count.
  return (
    <span className="mt-0.5 flex items-center gap-1 whitespace-nowrap text-[11px] font-normal text-[#c9d3e4]"
      title={`${n} held items in the whole backlog, across every Brief`}>
      <span className="rounded-full bg-[#f59e0b] px-1.5 font-semibold text-navy tabular-nums">{n}</span> total backlog
    </span>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  return (
    <div className="grid min-h-screen grid-cols-1 grid-rows-[56px_auto_1fr] md:grid-cols-[196px_minmax(0,1fr)] md:grid-rows-[56px_1fr]">
      <header className="col-span-full flex items-center gap-3.5 bg-navy px-5 text-[#e8edf5]">
        <Link href="/brief" className="flex items-center" aria-label="Jessie home">
          <Image src="/logo.png" alt="Jessie" width={145} height={34} priority className="h-[34px] w-auto" />
        </Link>
        <span className="h-6 w-px bg-[#2c3d63]" />
        <span className="hidden text-sm text-[#c9d3e4] sm:inline">Competitive intelligence</span>
        <span className="hidden text-sm italic text-jgreen lg:inline">Make knowledge impossible to miss</span>
        <span className="flex-1" />
        <RunPill />
      </header>
      <aside className="border-t border-[#1e2f55] bg-navy px-2 py-2.5">
        <nav aria-label="Screens" className="sticky top-2 flex flex-row flex-wrap gap-0.5 md:flex-col">
          {NAV.map((g) => (
            <div key={g.group} className="contents md:block">
              <span className="mx-2.5 mb-1.5 mt-3.5 hidden text-[11px] uppercase tracking-[.06em] text-[#7f8eac] md:block">{g.group}</span>
              {g.items.map((it) => {
                const active = path === it.href || path.startsWith(`${it.href}/`);
                const Icon = it.icon;
                return (
                  <Link
                    key={it.href}
                    href={it.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "relative flex items-center gap-2.5 rounded-md px-2.5 py-[9px] text-[13px] text-[#b9c5dc] hover:bg-navy2 hover:text-white",
                      active && "bg-navy2 font-semibold text-white before:absolute before:-left-2 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-r before:bg-jgreen",
                    )}
                  >
                    <Icon className="size-[18px] shrink-0" strokeWidth={1.7} />
                    <span className="flex min-w-0 flex-col">
                      {it.label}
                      {it.badge === "review" ? <ReviewCount /> : null}
                    </span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>
      <main className="flex min-w-0 flex-col gap-[18px] px-4 pb-10 pt-5 sm:px-6">
        <ItemDrawerProvider>{children}</ItemDrawerProvider>
      </main>
    </div>
  );
}
