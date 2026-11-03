"use client";
// Small shared pieces in the prototype's style. All API strings are rendered as React text (D32).
import type { ReactNode } from "react";
import { AlertTriangle, ExternalLink, Inbox, Info, RefreshCw } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ApiError } from "@/lib/api";
import { CATEGORY_COLOR, RUBRIC, SCORE_COLOR, STATUS_COLOR, STATUS_LABEL, UNVERIFIED_VALUES, label, publisherName, safeHref } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A small (i) that explains on hover and keyboard focus: long explanations live here, not on screen. */
export function InfoHint({ text, label: aria = "What this means" }: { text: ReactNode; label?: string }) {
  if (!text) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" aria-label={aria} data-info-hint
          className="inline-flex size-4 shrink-0 items-center justify-center rounded-full align-middle text-mute outline-none hover:text-jgreen-d focus-visible:ring-2 focus-visible:ring-jgreen">
          <Info className="size-3.5" aria-hidden />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-left font-normal">{text}</TooltipContent>
    </Tooltip>
  );
}

export function PageHead({ title, sub, tools, info, icon, titleHint }: {
  title: string; sub?: ReactNode; tools?: ReactNode; info?: ReactNode; icon?: ReactNode; titleHint?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5">
      <div>
        <h1 className="m-0 flex items-center gap-1.5 text-[1.375rem] font-semibold">
          {icon}
          {titleHint ? <Hint text={titleHint}>{title}</Hint> : title}
          <InfoHint text={info} />
        </h1>
        {sub ? <div className="mt-0.5 text-mute">{sub}</div> : null}
      </div>
      {tools ? <div className="flex flex-wrap items-center gap-2">{tools}</div> : null}
    </div>
  );
}

/** A white card with a question as its title (prototype .card / .ct). */
/** D88: the AI-extracted values are unverified; always visible, never only on hover. */
export function UnverifiedNote({ className }: { className?: string }) {
  return (
    <p className={cn("m-0 flex items-start gap-1.5 rounded border border-[#f3d9a4] bg-[#fffaf0] px-2.5 py-1.5 text-xs text-[#5c4300]", className)} data-unverified>
      <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
      <span>{UNVERIFIED_VALUES}</span>
    </p>
  );
}

export function Panel({ title, cap, children, className, right, big, info }: {
  title?: ReactNode; cap?: ReactNode; children: ReactNode; className?: string; right?: ReactNode; big?: boolean; info?: ReactNode;
}) {
  return (
    <section className={cn("min-w-0 rounded-md border border-line bg-card px-[1.125rem] py-4", className)}>
      {title || cap || right ? (
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          {title ? <h2 className={cn("m-0 flex items-center gap-1.5 font-semibold", big ? "text-lg" : "text-sm")}>{title}<InfoHint text={info} /></h2> : <span />}
          <div className="flex items-baseline gap-3">
            {cap ? <span className="text-xs text-mute">{cap}</span> : null}
            {right}
          </div>
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function ScoreBadge({ score, noise, title }: { score: number | null; noise?: boolean; title?: string }) {
  const n = noise ? 0 : (score ?? 0);
  const [bg, fg] = SCORE_COLOR[n] ?? SCORE_COLOR[0];
  return (
    <span
      className="inline-flex h-6 min-w-[1.625rem] shrink-0 items-center justify-center rounded px-[0.4375rem] text-xs font-semibold tabular-nums"
      style={{ background: bg, color: fg }}
      title={title ?? (noise ? "Noise" : score ? `Importance ${score} of 5` : "No score")}
    >
      {noise ? "N" : score ? String(score) : "–"}
    </span>
  );
}

export function StatusDot({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs">
      <i className="inline-block size-2 rounded-full" style={{ background: STATUS_COLOR[status] ?? "#cbd3df" }} />
      {label(STATUS_LABEL, status)}
    </span>
  );
}

export function Tag({ children, className, style, title }: { children: ReactNode; className?: string; style?: React.CSSProperties; title?: string }) {
  return (
    <span title={title} style={style} className={cn("inline-block rounded-[3px] bg-track px-2 py-px text-xs text-[#44516a]", className)}>
      {children}
    </span>
  );
}

export function CategoryTag({ category }: { category: string | null }) {
  if (!category) return <Tag>No category</Tag>;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[#44516a]">
      <i className="inline-block size-2 rounded-sm" style={{ background: CATEGORY_COLOR[category] ?? "#9aa5b5" }} />
      {category}
    </span>
  );
}

/** An explanation on hover and on keyboard focus. The trigger is focusable; pass asChild when the child already is. */
export function Hint({ text, children, asChild = false, className }: { text: ReactNode; children: ReactNode; asChild?: boolean; className?: string }) {
  if (!text) return <>{children}</>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {asChild ? children : <span tabIndex={0} className={cn("cursor-help rounded outline-none focus-visible:ring-2 focus-visible:ring-jgreen", className)}>{children}</span>}
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-left">{text}</TooltipContent>
    </Tooltip>
  );
}

/** A visible colour legend: every colour that carries meaning is named on screen, never only in a hover. */
export function ColorLegend({ title, items, className }: {
  title?: ReactNode; items: { color: string; label: ReactNode; fg?: string; text?: string }[]; className?: string;
}) {
  if (!items.length) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] text-mute", className)} data-legend>
      {title ? <span className="font-semibold">{title}</span> : null}
      {items.map((it, i) => (
        <span key={i} className="inline-flex items-center gap-1">
          {it.text ? (
            <i className="inline-flex h-3.5 min-w-3.5 items-center justify-center rounded-[3px] px-0.5 text-[0.5625rem] font-semibold not-italic tabular-nums"
              style={{ background: it.color, color: it.fg }}>{it.text}</i>
          ) : (
            <i className="inline-block size-2.5 rounded-sm ring-1 ring-black/10" style={{ background: it.color }} aria-hidden />
          )}
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** The category colours, for the categories shown (or every category). */
export function CategoryLegend({ categories, title = "Categories:" }: { categories: string[]; title?: ReactNode }) {
  return <ColorLegend title={title} items={categories.map((c) => ({ color: CATEGORY_COLOR[c] ?? "#9aa5b5", label: c }))} />;
}

/** The two colour legends every item view shows, always visible: Importance (score colours) and Category. */
export function ColourLegends({ unscored = false, className }: { unscored?: boolean; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1 rounded-md border border-line bg-card px-3 py-2", className)} aria-label="Colour legend" data-legends>
      <ImportanceLegend unscored={unscored} />
      <CategoryColours />
    </div>
  );
}

/** "Importance (1–5)": the score colours, 5 to 1, with the rubric's names; N and – when the view shows them. */
export function ImportanceLegend({ unscored = false, className }: { unscored?: boolean; className?: string }) {
  const extra = unscored ? [
    { color: SCORE_COLOR[0][0], fg: SCORE_COLOR[0][1], text: "N", label: "noise" },
    { color: SCORE_COLOR[0][0], fg: SCORE_COLOR[0][1], text: "–", label: "not scored" },
  ] : [];
  return (
    <ColorLegend className={className} title="Importance (1–5)" items={[5, 4, 3, 2, 1].map((n) => ({
      color: SCORE_COLOR[n][0], fg: SCORE_COLOR[n][1], text: String(n), label: RUBRIC[n]?.label ?? null,
    })).concat(extra)} />
  );
}

/** "Category": all seven category colours, in one fixed order. */
export function CategoryColours({ className }: { className?: string }) {
  return <div className={className}><CategoryLegend title="Category" categories={Object.keys(CATEGORY_COLOR)} /></div>;
}

/** "n=12" next to every eval number and every measured count. */
export function N({ n }: { n: number | null | undefined }) {
  return <span className="ml-1 text-[0.6875rem] font-normal text-mute tabular-nums">n={n ?? "?"}</span>;
}

/** External links only open http(s) URLs (D32); safeHref turns anything else into no link. */
export const ARTICLE_LINK_LABEL = "Open the original article in a new tab";

/** The one external-link style: the publisher's name (D90; the article's domain for an aggregator or a missing
 *  publisher; "Source" only when there is neither) with the external-link icon (box with arrow), opening the original
 *  page in a new tab. A long name is cut to one line, the full name on hover. Nothing when the URL isn't http(s).
 *  `publisher` is only for an article link: a tracked or source page keeps "Source". */
export function ArticleLink({ href, label: aria = ARTICLE_LINK_LABEL, className, iconOnly = false, publisher }: {
  href: string | null | undefined; label?: string; className?: string; iconOnly?: boolean; publisher?: string | null;
}) {
  const safe = safeHref(href);
  if (!safe) return null;
  const name = publisher !== undefined ? publisherName(publisher, safe) : null;
  const text = name ?? "Source";
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer nofollow" aria-label={name ? `${aria}: ${name}` : aria}
      title={name ? `${name} · ${aria}` : iconOnly ? "Source" : aria}
      onClick={(e) => e.stopPropagation()} data-publisher={name ?? undefined}
      className={cn("inline-flex min-w-0 shrink-0 items-center gap-0.5 whitespace-nowrap rounded text-[0.6875rem] font-normal text-mute hover:text-jgreen-d hover:underline focus-visible:outline-2 focus-visible:outline-jgreen", className)}>
      {iconOnly ? null : <span className={name ? "max-w-[14rem] truncate" : undefined}>{text}</span>}
      <ExternalLink className={cn("shrink-0", iconOnly ? "size-3.5" : "size-3")} aria-hidden="true" />
    </a>
  );
}

/** The one link convention for an item: the title opens the side drawer, the publisher's name opens the original
 *  article (D90). */
export function ItemTitle({ title, url, onOpen, className, publisher }: {
  title: string; url?: string | null; onOpen?: () => void; className?: string; publisher?: string | null;
}) {
  const text = title || "(no title)";
  return (
    <span className="inline-flex min-w-0 flex-wrap items-start gap-x-1">
      {onOpen ? (
        <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(); }} title="Open the details"
          className={cn("min-w-0 text-left hover:text-jgreen-d hover:underline", className)}>{text}</button>
      ) : (
        <span className={cn("min-w-0", className)}>{text}</span>
      )}
      <ArticleLink href={url} className="mt-0.5" publisher={publisher} />
    </span>
  );
}

// ---- loading, empty and error states (every API call) ----

export function Loading({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-5 w-full bg-track" style={{ width: `${100 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 py-3 text-mute">
      <Inbox className="size-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  const code = "code" in error ? (error as ApiError).code : undefined;
  return (
    <div role="alert" className="flex flex-wrap items-center gap-2 rounded border-l-[3px] border-[#d14343] bg-[#fff5f5] px-3 py-2">
      <AlertTriangle className="size-4 shrink-0 text-[#d14343]" />
      <span className="flex-1">
        {error.message}
        {code ? <span className="ml-2 text-xs text-mute">({code})</span> : null}
      </span>
      {onRetry ? (
        <Button size="sm" variant="outline" onClick={onRetry} className="h-7 text-xs">
          <RefreshCw className="size-3" /> Retry
        </Button>
      ) : null}
    </div>
  );
}

/** Renders loading, error or empty for one SWR result, else its children. */
export function Async<T>({ data, error, isLoading, retry, empty, isEmpty, rows, children }: {
  data: T | undefined;
  error: ApiError | undefined;
  isLoading: boolean;
  retry?: () => void;
  empty?: ReactNode;
  isEmpty?: (d: T) => boolean;
  rows?: number;
  children: (d: T) => ReactNode;
}) {
  if (error && !data) return <ErrorNote error={error} onRetry={retry} />;
  if (!data) return isLoading ? <Loading rows={rows} /> : <Empty>No data.</Empty>;
  if (isEmpty?.(data)) return <Empty>{empty ?? "Nothing here."}</Empty>;
  return (
    <>
      {error ? <ErrorNote error={error} onRetry={retry} /> : null}
      {children(data)}
    </>
  );
}

/** Horizontal bars (prototype .hb). */
export function HBars({ rows, color = "var(--bar)", max: fixedMax }: { rows: { label: string; value: number; color?: string; title?: string }[]; color?: string; max?: number }) {
  const max = fixedMax ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <div>
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[8.5rem_minmax(0,1fr)_2.4rem] items-center gap-2.5 py-[0.3125rem]" title={r.title}>
          <span className="truncate">{r.label}</span>
          <div className="h-2.5 overflow-hidden rounded-sm bg-track">
            <i className="block h-full rounded-sm" style={{ width: `${(100 * r.value) / max}%`, background: r.color ?? color }} />
          </div>
          <b className="text-right font-semibold tabular-nums">{r.value}</b>
        </div>
      ))}
    </div>
  );
}

/** The 4 KPI tiles. */
export function KpiTile({ value, label: l, sub, future = false }: { value: ReactNode; label: string; sub?: ReactNode; future?: boolean }) {
  return (
    <div className={cn("rounded-md border border-line bg-card px-[1.125rem] py-4", future && "border-dashed opacity-70")} data-future={future ? "1" : undefined}>
      <div className="text-[1.875rem] font-semibold leading-[1.1] tabular-nums">{value}</div>
      <div className="mt-1 flex items-center gap-1.5 text-mute">
        {l}
        {future ? <Tag className="bg-[#e8eefb] text-[0.625rem] font-semibold uppercase tracking-wide text-[#3f5b8f]">Future</Tag> : null}
      </div>
      {sub ? <div className="mt-1.5 text-xs">{sub}</div> : null}
    </div>
  );
}

/** A click anywhere on an item row or card opens the item's drawer, except on its own controls (buttons, links, fields, menus),
 *  inside a dialog or menu rendered elsewhere (React bubbles portal clicks), or when the user is selecting text.
 *  Keyboard users open it with the title button. */
const INTERACTIVE = "button, a, input, textarea, select, label, [role='menuitem'], [role='menu'], [role='dialog'], [role='radio']";
export function openFromRow(e: React.MouseEvent<HTMLElement>, open: () => void) {
  const t = e.target as HTMLElement;
  if (!e.currentTarget.contains(t)) return; // a portal (Edit dialog, Dismiss menu)
  if (t.closest(INTERACTIVE)) return;
  if (typeof window !== "undefined" && window.getSelection()?.toString()) return;
  open();
}
