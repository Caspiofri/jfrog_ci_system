"use client";
import { Async, ColourLegends, Empty, PageHead, Panel } from "@/components/ci";
import { CompetitorCardView, DealsTable } from "@/components/competitors/parts";
import { CapabilityMatrix } from "@/components/competitors/Matrix";
import { ActivityHeatmap } from "@/components/competitors/Heatmap";
import { useApi } from "@/lib/api";
import { LEVEL_LABEL, fmtDate, label } from "@/lib/format";
import type { Competitors } from "@/lib/types";

export default function CompetitorsPage() {
  const q = useApi<Competitors>("/api/v1/competitors");
  return (
    <>
      <PageHead title="Competitors" info="Top score is the highest score of any item this week." />
      <CapabilityMatrix />
      <ActivityHeatmap />
      <Async {...q} retry={() => q.mutate()} rows={6} isEmpty={(d) => !d.items.length} empty="No competitors in the config.">
        {(d) => (
          <>
            <div className="-mt-2 text-xs text-mute">
              Week {fmtDate(d.week.start)}–{fmtDate(d.week.end)}, counted by discovery time; published items only
              (held items count as awaiting review at {label(LEVEL_LABEL, d.level)}).
            </div>
            <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))]">
              {d.items.map((c) => <CompetitorCardView key={c.key} c={c} />)}
            </div>
            <ColourLegends />
            <Panel title="Who is buying and partnering?" cap={`${d.deals.category} items as collected · ${d.deals.total} items`}>
              {d.deals.items.length ? <DealsTable deals={d.deals.items} /> : <Empty>No funding, M&amp;A or partnership items yet.</Empty>}
              <div className="mt-2 text-[11px] text-mute">
                Deal type, buyer and target aren&apos;t extracted yet (Roadmap). M&amp;A items are held at every level, so they show &ldquo;Awaiting review&rdquo; until approved.
              </div>
            </Panel>
          </>
        )}
      </Async>
    </>
  );
}
