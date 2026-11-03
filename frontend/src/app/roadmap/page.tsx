"use client";
// Roadmap (D35): concepts from the design prototype that need data the pipeline doesn't produce yet.
// The only screen with sample data, and only inside the screenshots. Drop each image at
// frontend/public/roadmap/<slug>.png (the prototype's own screenshots, unedited); a slot appears only once its image
// loads, so with no image there is no slot. The concept's text shows either way.
import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { PageHead } from "@/components/ci";
import { cn } from "@/lib/utils";

// wide: a full row (the two very wide images, which are unreadable at half width on a 1366 screen)
const CONCEPTS: { slug: string; title: string; shows: string; missing: string; screen: string; wide?: boolean }[] = [
  {
    slug: "strength-radar",
    title: "Where is their shape different?",
    screen: "Competitor profile",
    shows: "a competitor's strength against JFrog on each of the 7 axes, scored 1 to 5.",
    missing: "a strength score per axis, set or checked by a product expert.",
  },
  {
    slug: "convergence",
    title: "Are they getting closer to JFrog?",
    screen: "Competitor profile",
    shows: "how many of the 7 axes a competitor shares with JFrog, month by month.",
    missing: "a checked yes/no per axis and monthly history.",
  },
  {
    slug: "topics",
    wide: true,
    title: "Where is the market heading?",
    screen: "Competitors · Market view",
    shows: "which competitors moved on each market topic this month.",
    missing: "a stable topic list and monthly history per competitor.",
  },
  {
    slug: "reactions",
    wide: true,
    title: "Who reacts to market events, and how fast?",
    screen: "Brief · Competitors",
    shows: "how many days each competitor took to respond to a market event.",
    missing: "reliable linking of a competitor's response to the event that caused it.",
  },
  {
    slug: "pressure",
    title: "Where is the pressure on JFrog?",
    screen: "Brief",
    shows: "where competitor moves press on each JFrog product, and where a gap exists.",
    missing: "a checked product mapping per item and verified gaps.",
  },
  {
    slug: "emerging",
    title: "Who else is rising?",
    screen: "Competitors · Market view",
    shows: "rising companies outside the tracked list, with mention trends.",
    missing: "automatic discovery of new companies and a mention baseline.",
  },
  {
    slug: "deal-extraction",
    title: "Deals: buyer, target and type",
    screen: "Competitors",
    shows: "deals across the market, with parties and deal type.",
    missing: "extraction of buyer, target and deal type. The product's real deals block lists items as they are.",
  },
];

/** The concept's screenshot slot (D104): hidden until the image loads, gone if there is none, so never an empty frame.
 *  The image is shown whole and centred in a fixed 18rem frame (never cropped, stretched or enlarged), with "Concept,
 *  sample data" in its frame, directly against the image. While it loads the frame keeps its place, invisible. */
function Shot({ slug, title }: { slug: string; title: string }) {
  const [state, setState] = useState<"loading" | "ok" | "none">("loading");
  const img = useRef<HTMLImageElement | null>(null);
  // eager: a lazy image inside the hidden frame would never load. An image can also finish (or fail) before React
  // attaches onLoad/onError, so its state is read once on mount too
  useEffect(() => {
    const el = img.current;
    if (el?.complete) setState(el.naturalWidth > 0 ? "ok" : "none");
  }, []);
  if (state === "none") return null;
  return (
    <figure className={cn("m-0 flex flex-col overflow-hidden rounded border border-navy/40 bg-white", state !== "ok" && "invisible")} data-shot={slug}>
      {/* the label is part of the image's frame, directly against it, and covers none of the image */}
      <figcaption className="bg-navy px-2.5 py-1 text-[0.6875rem] font-semibold uppercase tracking-wide text-white" data-concept-label>{CONCEPT_LABEL}</figcaption>
      {/* a fixed-height frame: every card in a row lines up; the image sits whole and centred, never enlarged */}
      <div className="flex h-[18rem] items-center justify-center p-2" data-shot-frame>
        <Image ref={img} src={`/roadmap/${slug}.png`} alt={`${title}: concept screenshot with sample data`} width={0} height={0} sizes="100vw" unoptimized loading="eager"
          className="block h-auto max-h-full w-auto max-w-full" onLoad={() => setState("ok")} onError={() => setState("none")} />
      </div>
    </figure>
  );
}

const CONCEPT_LABEL = "Concept, sample data";

export default function RoadmapPage() {
  return (
    <>
      <PageHead title="Roadmap" info="Concepts from the design prototype that need data the pipeline doesn't produce yet." />
      <div className="-mt-2 text-xs text-mute">
        Every image here uses the prototype&apos;s sample data and isn&apos;t connected to the pipeline. The other screens show only real data.
      </div>
      {/* each card spans four rows of a subgrid (title, image, Would show, Missing), so the parts line up across a row;
          on half-width cards each line has a 2-line slot, so every half-width card is the same height */}
      <div className="grid gap-x-3.5 gap-y-3.5 md:grid-cols-2" data-roadmap-grid>
        {CONCEPTS.map((c) => (
          <section key={c.slug} className={cn("row-span-4 grid grid-rows-subgrid gap-2.5 rounded-md border border-line bg-card px-[1.125rem] py-4", c.wide && "md:col-span-2")}
            data-wide={c.wide || undefined}>
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="m-0 text-sm font-semibold">{c.title}</h2>
              <span className="text-[0.6875rem] text-mute">{c.screen}</span>
            </div>
            <Shot slug={c.slug} title={c.title} />
            <p className={cn("m-0 self-start", !c.wide && "md:min-h-[2lh]")}><span className="text-mute">Would show: </span>{c.shows}</p>
            <p className={cn("m-0 self-start", !c.wide && "md:min-h-[2lh]")}><span className="text-mute">Missing: </span>{c.missing}</p>
          </section>
        ))}
      </div>
    </>
  );
}
