"use client";
import { Async, Empty, InfoHint, PageHead, Panel } from "@/components/ci";
import { CompetitorCardView, DealsTable } from "@/components/competitors/parts";
import { CapabilityMatrix } from "@/components/competitors/Matrix";
import { ActivityHeatmap } from "@/components/competitors/Heatmap";
import { useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { SPARK_LINE } from "@/lib/sparkline";
import type { Competitors } from "@/lib/types";

const PAGE_INFO =
  "JFrog's tracked competitors and how they compare with JFrog: what each one's public pages state on the 7 JFrog capabilities, their cleared items by category, counted by the date collected this week, and a card per competitor with what is awaiting review and its top item. It shows what was found, not a verdict.";

const CARDS_EXPLAIN = "Each card shows the items awaiting review, the items that mention JFrog, cleared items per day and the week's top cleared item. Cleared means passed routing, or approved by an analyst.";

export default function CompetitorsPage() {
  const q = useApi<Competitors>("/api/v1/competitors");
  return (
    <>
      <PageHead title="Competitors" info={PAGE_INFO} />
      <CapabilityMatrix />
      <ActivityHeatmap />
      <Async {...q} retry={() => q.mutate()} rows={6} isEmpty={(d) => !d.items.length} empty="No competitors in the config.">
        {(d) => (
          <>
            <section className="flex flex-col gap-0.5" aria-label="Competitor overview" data-cards-header>
              <h2 className="m-0 flex flex-wrap items-center gap-1.5 text-lg font-semibold">
                Competitor overview
                <InfoHint text={CARDS_EXPLAIN} label="What the cards show" />
              </h2>
              <p className="m-0 text-sm text-mute" data-week-range>{fmtDate(d.week.start)}–{fmtDate(d.week.end)} · Select a card for the full profile</p>
              <p className="m-0 mt-1 text-xs text-mute" data-spark-line>{SPARK_LINE}</p>
            </section>
            <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))]">
              {d.items.map((c) => <CompetitorCardView key={c.key} c={c} />)}
            </div>
            <Panel title="Who is buying and partnering?" cap={`${d.deals.category} items as collected · ${d.deals.total} items`}>
              {d.deals.items.length ? <DealsTable deals={d.deals.items} /> : <Empty>No funding, M&amp;A or partnership items yet.</Empty>}
              <div className="mt-2 text-[0.6875rem] text-mute">
                Deal type, buyer and target aren&apos;t extracted yet (Roadmap). M&amp;A items are held at every level, so they show &ldquo;Awaiting review&rdquo; until approved.
              </div>
            </Panel>
          </>
        )}
      </Async>
    </>
  );
}
