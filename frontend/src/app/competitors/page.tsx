"use client";
import { Async, CategoryLegend, Empty, PageHead, Panel, ScoreLegend } from "@/components/ci";
import { CompetitorCardView, DealsTable } from "@/components/competitors/parts";
import { useApi } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { LEVEL_LABEL, fmtDate, label } from "@/lib/format";
import type { Competitors } from "@/lib/types";

/** The categories seen on the cards, in the config's order (unknown ones last). */
function legendCategories(seen: string[], order: string[] | undefined): string[] {
  const s = new Set(seen);
  const known = (order ?? []).filter((c) => s.has(c));
  return [...known, ...[...s].filter((c) => !known.includes(c)).sort()];
}

export default function CompetitorsPage() {
  const q = useApi<Competitors>("/api/v1/competitors");
  const { data: meta } = useMeta();
  return (
    <>
      <PageHead title="Competitors" info="Threat is the highest importance this week." />
      <Async {...q} retry={() => q.mutate()} rows={6} isEmpty={(d) => !d.items.length} empty="No competitors in the config.">
        {(d) => (
          <>
            <div className="-mt-2 text-xs text-mute">
              Week {fmtDate(d.week.start)}–{fmtDate(d.week.end)}, counted by discovery time; published items only
              (held items count as awaiting review at {label(LEVEL_LABEL, d.level)}).
            </div>
            <div className="flex flex-col gap-1 rounded-md border border-line bg-card px-3 py-2" aria-label="Colour legend">
              <ScoreLegend title="Threat colour (highest score this week):" />
              <CategoryLegend title="Category bar:" categories={legendCategories(d.items.flatMap((c) => c.category_mix.map((m) => m.category)), meta?.categories)} />
            </div>
            <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))]">
              {d.items.map((c) => <CompetitorCardView key={c.key} c={c} />)}
            </div>
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
