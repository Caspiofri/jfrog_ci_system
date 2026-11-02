"use client";
import { Async, ColourLegends, Empty, InfoHint, PageHead, Panel } from "@/components/ci";
import { CompetitorCardView, DealsTable } from "@/components/competitors/parts";
import { CapabilityMatrix } from "@/components/competitors/Matrix";
import { ActivityHeatmap } from "@/components/competitors/Heatmap";
import { useApi } from "@/lib/api";
import { cardTotals } from "@/lib/cardTotals";
import { LEVEL_LABEL, fmtDate, label } from "@/lib/format";
import type { Competitors } from "@/lib/types";

const CARDS_EXPLAIN =
  "Each card counts a competitor's relevant articles found in the last 7 days. The big number is what was published to analysts; items still queued for an analyst are not in it and show as \"awaiting review\". Noise and dismissed items are left out. The Industry card holds market news with no tracked competitor.";

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
            <section className="flex flex-col gap-1" aria-label="Published competitor items" data-cards-header>
              <h2 className="m-0 flex flex-wrap items-center gap-1.5 text-lg font-semibold">
                Published competitor items <span className="text-sm font-normal text-mute">· found {fmtDate(d.week.start)}–{fmtDate(d.week.end)}</span>
                <InfoHint text={`${CARDS_EXPLAIN} Queue level: ${label(LEVEL_LABEL, d.level)}.`} label="What the cards count" />
              </h2>
              <p className="m-0 flex flex-wrap items-baseline gap-x-3 text-sm">
                <span><b className="text-xl font-semibold tabular-nums">{cardTotals(d.items).published}</b> published</span>
                <span><b className="text-xl font-semibold tabular-nums text-[#8a5a00]">{cardTotals(d.items).queued}</b> awaiting review</span>
                <span className="text-xs text-mute">across the six competitors</span>
              </p>
            </section>
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
