"use client";
// Roadmap (D35): concepts from the design prototype that need data the pipeline doesn't produce yet.
// The only screen with sample data, and only inside the screenshots. Drop each image at public/roadmap/<slug>.png.
import { useState } from "react";
import Image from "next/image";
import { ImageIcon } from "lucide-react";
import { PageHead } from "@/components/ci";

const CONCEPTS: { slug: string; title: string; shows: string; missing: string; screen: string }[] = [
  {
    slug: "market-view",
    title: "Market view",
    screen: "Competitors",
    shows: "The market beyond the six named competitors: where it is heading, who is rising, deals and reactions in one view.",
    missing: "Topic tags, other-vendor mentions and event clustering; each block below names its own gap.",
  },
  {
    slug: "topics",
    title: "Where is the market heading?",
    screen: "Competitors · Market view",
    shows: "Topic × competitor grid: which competitors moved on each topic this month vs last.",
    missing: "Topic tagging of items; the classifier assigns a category, not a topic.",
  },
  {
    slug: "emerging",
    title: "Who else is rising?",
    screen: "Competitors · Market view",
    shows: "Companies outside the tracked list, with 30-day mentions, trend and a watchlist button.",
    missing: "The classifier recording other vendors named in an item (e.g. Socket, Aikido); auto-discovery is future scope.",
  },
  {
    slug: "reactions",
    title: "Who reacts to market events, and how fast?",
    screen: "Brief · Competitors",
    shows: "A market event and the days until each competitor responded.",
    missing: "The event model: linking a market event to each competitor's response; events aren't built yet (contract §1).",
  },
  {
    slug: "deal-extraction",
    title: "Deals: buyer, target and type",
    screen: "Competitors",
    shows: "Each funding, M&A or partnership item split into type (acquisition, funding, partnership), actor and target.",
    missing: "An extraction step; today the deals block lists the items as collected.",
  },
  {
    slug: "strength-radar",
    title: "Where is their shape different?",
    screen: "Competitor profile",
    shows: "Strength on each of the 7 axes, 1 to 5, for the competitor beside JFrog.",
    missing: "A scoring method for strength per axis; head-to-head cells hold text values, not scores.",
  },
  {
    slug: "convergence",
    title: "Are they getting closer to JFrog?",
    screen: "Competitor profile",
    shows: "Axes of 7 where the competitor overlaps with JFrog, month by month.",
    missing: "Monthly history of head-to-head cells and an overlap rule; cell history starts on Oct 30, 2026.",
  },
  {
    slug: "team-chips",
    title: "Who is each insight for?",
    screen: "Brief insights",
    shows: "Audience chips (Product, Sales, Strategy, Marketing, Pricing, Executive) and a suggested action on every insight.",
    missing: "The insights generator produces no audience or action; role-based digests are future scope.",
  },
  {
    slug: "battlefield",
    title: "Where is the pressure on JFrog?",
    screen: "Brief",
    shows: "JFrog products (Curation, Xray, Artifactory, AI/MCP) × competitors, each cell the day's top importance.",
    missing: "jfrog_product per item and the capability baseline; per-competitor profiles replaced the single matrix for now.",
  },
];

function Shot({ slug, title }: { slug: string; title: string }) {
  const [missing, setMissing] = useState(false);
  return (
    <div className="relative aspect-[16/10] overflow-hidden rounded border border-dashed border-input bg-page">
      {!missing ? (
        <Image src={`/roadmap/${slug}.png`} alt={`${title}: concept screenshot with sample data`} fill unoptimized
          className="object-cover object-top" onError={() => setMissing(true)} />
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-1.5 text-mute">
          <ImageIcon className="size-6" />
          <span className="text-xs">Screenshot to add: public/roadmap/{slug}.png</span>
        </div>
      )}
      <span className="absolute left-2 top-2 rounded bg-navy/90 px-2 py-0.5 text-[11px] font-semibold text-white">Concept, sample data</span>
    </div>
  );
}

export default function RoadmapPage() {
  return (
    <>
      <PageHead title="Roadmap" sub="Concepts from the design prototype that need data the pipeline doesn't produce yet" />
      <div className="-mt-2 text-xs text-mute">
        Every image here uses the prototype&apos;s sample data and isn&apos;t connected to the pipeline. The other screens show only real data.
      </div>
      <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,22rem),1fr))]">
        {CONCEPTS.map((c) => (
          <section key={c.slug} className="flex flex-col gap-2.5 rounded-md border border-line bg-card px-[18px] py-4">
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="m-0 text-sm font-semibold">{c.title}</h2>
              <span className="text-[11px] text-mute">{c.screen}</span>
            </div>
            <Shot slug={c.slug} title={c.title} />
            <p className="m-0"><span className="text-mute">Would show: </span>{c.shows}</p>
            <p className="m-0"><span className="text-mute">Missing: </span>{c.missing}</p>
          </section>
        ))}
      </div>
    </>
  );
}
