"use client";
// Review queue filter bar (UI polish, 3 Nov evening): a segmented status control, quiet sort text, and filter chips.
// Every control is the same Radix Select (or buttons) as before, so keyboard use and the URL state are unchanged.
// The menus use popper positioning: the triggers show their own text instead of <SelectValue>, which Radix's
// item-aligned mode needs to move focus into the list.
// The accent tint marks "active filter" only; it carries no other meaning.
import { ArrowUpDown, X } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const ALL = "__all__";
type Opt = { value: string; label: string };

/** One filter as a chip. Inactive: dashed hairline, the name and a chevron. Active: tinted, "Name: value", and an x
 *  that clears only this filter. "" means no filter, as in FilterSelect. */
export function FilterChip({ name, ariaLabel, allLabel, value, onChange, options, display }: {
  name: string; ariaLabel: string; allLabel: string; value: string; onChange: (v: string) => void; options: Opt[];
  display?: (o: Opt) => string; // a shorter text for the active chip (e.g. the Brief day)
}) {
  const cur = options.find((o) => o.value === value);
  const active = Boolean(value);
  return (
    <span className={cn("inline-flex h-7 items-center rounded-full border text-xs",
      active ? "border-jgreen/50 bg-accent text-ink" : "border-dashed border-line bg-white text-[#44516a]")} data-filter-chip={ariaLabel} data-active={active || undefined}>
      <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? "" : v)}>
        <SelectTrigger aria-label={ariaLabel} size="sm"
          className="h-7 gap-1 rounded-full border-0 bg-transparent px-2.5 text-xs shadow-none focus-visible:ring-2 [&_svg]:size-3">
          <span className={active ? "font-semibold" : undefined}>
            {active ? `${name}: ${cur ? (display ? display(cur) : cur.label) : value}` : name}
          </span>
        </SelectTrigger>
        <SelectContent position="popper" align="start">
          <SelectItem value={ALL}>{allLabel}</SelectItem>
          {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>
      {active ? (
        <button type="button" onClick={() => onChange("")} aria-label={`Clear ${name.toLowerCase()} filter`} title={`Clear ${name.toLowerCase()} filter`}
          className="-ml-1 mr-1 grid size-5 place-items-center rounded-full text-mute hover:bg-white hover:text-ink focus-visible:outline-2 focus-visible:outline-jgreen">
          <X className="size-3" aria-hidden />
        </button>
      ) : null}
    </span>
  );
}

/** The status control: segmented buttons for up to three options, else one pill dropdown (the same Select). */
export function StatusControl({ ariaLabel, value, onChange, options }: {
  ariaLabel: string; value: string; onChange: (v: string) => void; options: Opt[];
}) {
  if (options.length <= 3) {
    return (
      <div role="group" aria-label={ariaLabel} className="inline-flex h-8 shrink-0 items-center rounded-full border border-line bg-page p-0.5" data-status-control="segmented">
        {options.map((o) => (
          <button key={o.value || "default"} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}
            className={cn("h-7 whitespace-nowrap rounded-full px-3 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-jgreen",
              value === o.value ? "bg-white font-semibold text-ink shadow-sm ring-1 ring-line" : "text-mute hover:text-ink")}>
            {o.label}
          </button>
        ))}
      </div>
    );
  }
  const cur = options.find((o) => o.value === value) ?? options[0];
  return (
    <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? "" : v)}>
      <SelectTrigger aria-label={ariaLabel} size="sm" className="h-8 shrink-0 rounded-full bg-white px-3 text-xs" data-status-control="dropdown">
        <span className="font-semibold">{cur.label}</span>
      </SelectTrigger>
      <SelectContent position="popper" align="start">
        {options.map((o) => <SelectItem key={o.value || ALL} value={o.value || ALL}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

/** "Sort: Importance" as quiet text with a small dropdown (the UI sorts the whole queue in the browser). */
export function SortControl({ ariaLabel, allLabel, value, onChange, options }: {
  ariaLabel: string; allLabel: string; value: string; onChange: (v: string) => void; options: Opt[];
}) {
  const cur = options.find((o) => o.value === value)?.label ?? allLabel;
  return (
    <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? "" : v)}>
      <SelectTrigger aria-label={ariaLabel} size="sm"
        className="h-8 shrink-0 gap-1 border-0 bg-transparent px-1.5 text-xs text-mute shadow-none hover:text-ink [&_svg]:size-3">
        <ArrowUpDown className="size-3.5" aria-hidden />
        <span>Sort: <span className="font-semibold text-ink">{cur}</span></span>
      </SelectTrigger>
      <SelectContent position="popper" align="end">
        <SelectItem value={ALL}>{allLabel}</SelectItem>
        {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

