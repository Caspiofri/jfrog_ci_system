"use client";
// Small shared pieces in the prototype's style. All API strings are rendered as React text (D32).
import type { ReactNode } from "react";
import { AlertTriangle, ArrowUpRight, Inbox, RefreshCw } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ApiError } from "@/lib/api";
import { CATEGORY_COLOR, SCORE_COLOR, STATUS_COLOR, STATUS_LABEL, label, safeHref } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PageHead({ title, sub, tools }: { title: string; sub?: ReactNode; tools?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5">
      <div>
        <h1 className="m-0 text-[22px] font-semibold">{title}</h1>
        {sub ? <div className="mt-0.5 text-mute">{sub}</div> : null}
      </div>
      {tools ? <div className="flex flex-wrap items-center gap-2">{tools}</div> : null}
    </div>
  );
}

/** A white card with a question as its title (prototype .card / .ct). */
export function Panel({ title, cap, children, className, right, big }: {
  title?: ReactNode; cap?: ReactNode; children: ReactNode; className?: string; right?: ReactNode; big?: boolean;
}) {
  return (
    <section className={cn("min-w-0 rounded-md border border-line bg-card px-[18px] py-4", className)}>
      {title || cap || right ? (
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          {title ? <h2 className={cn("m-0 font-semibold", big ? "text-lg" : "text-sm")}>{title}</h2> : <span />}
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
      className="inline-flex h-6 min-w-[26px] shrink-0 items-center justify-center rounded px-[7px] text-xs font-semibold tabular-nums"
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

/** "n=12" next to every eval number and every measured count. */
export function N({ n }: { n: number | null | undefined }) {
  return <span className="ml-1 text-[11px] font-normal text-mute tabular-nums">n={n ?? "?"}</span>;
}

/** External links only open http(s) URLs (D32); safeHref turns anything else into no link. */
export const ARTICLE_LINK_LABEL = "Open the original article in a new tab";

/** The one external-link style: a ↗ icon that opens the original page in a new tab. Nothing when the URL isn't http(s). */
export function ArticleLink({ href, label: aria = ARTICLE_LINK_LABEL, className }: { href: string | null | undefined; label?: string; className?: string }) {
  const safe = safeHref(href);
  if (!safe) return null;
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer nofollow" aria-label={aria} title={aria}
      onClick={(e) => e.stopPropagation()}
      className={cn("inline-flex shrink-0 items-center rounded text-mute hover:text-jgreen-d focus-visible:outline-2 focus-visible:outline-jgreen", className)}>
      <ArrowUpRight className="size-3.5" aria-hidden="true" />
    </a>
  );
}

/** The one link convention for an item: the title opens the side drawer, the ↗ icon opens the original article. */
export function ItemTitle({ title, url, onOpen, className }: {
  title: string; url?: string | null; onOpen?: () => void; className?: string;
}) {
  const text = title || "(no title)";
  return (
    <span className="inline-flex min-w-0 items-start gap-1">
      {onOpen ? (
        <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(); }} title="Open the details"
          className={cn("min-w-0 text-left hover:text-jgreen-d hover:underline", className)}>{text}</button>
      ) : (
        <span className={cn("min-w-0", className)}>{text}</span>
      )}
      <ArticleLink href={url} className="mt-0.5" />
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
        <div key={r.label} className="grid grid-cols-[8.5rem_minmax(0,1fr)_2.4rem] items-center gap-2.5 py-[5px]" title={r.title}>
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
export function KpiTile({ value, label: l, sub }: { value: ReactNode; label: string; sub?: ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-card px-[18px] py-4">
      <div className="text-[30px] font-semibold leading-[1.1] tabular-nums">{value}</div>
      <div className="mt-1 text-mute">{l}</div>
      {sub ? <div className="mt-1.5 text-xs">{sub}</div> : null}
    </div>
  );
}
