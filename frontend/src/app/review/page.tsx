"use client";
import { Suspense, useState } from "react";
import { Check, ChevronDown, Pencil, ShieldCheck, Undo2, X } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Async, Empty, ErrorNote, ExtLink, HBars, Loading, N, PageHead, Panel, Tag } from "@/components/ci";
import { Donut } from "@/components/Donut";
import { FilterSelect } from "@/components/FilterSelect";
import { ItemRow } from "@/components/ItemRow";
import { ItemActions, useRefreshAll } from "@/components/review/actions";
import { ApiError, path, send, useApi } from "@/lib/api";
import { HOLD_LABEL, LEVEL_LABEL, fmtDateTime, fmtLongDate, label } from "@/lib/format";
import { competitorName, useMeta } from "@/lib/meta";
import { useUrlState } from "@/lib/useParams";
import type { HoldReason, Level, Page, Review, ReviewChangeRow, ReviewItemRow, SourceRow, TrustResult } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE = 25;
const LEVEL_HELP: Record<Level, string> = {
  strict: "Every unvetted source is held, plus everything always held",
  balanced: "Unvetted sources held only at importance 4 or 5",
  relaxed: "Only the always-held reasons: pricing, M&A, Mentions JFrog, changed cells, failures",
};

export default function ReviewPage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <ReviewScreen />
    </Suspense>
  );
}

function ReviewScreen() {
  const { get, set } = useUrlState();
  const { data: meta } = useMeta();
  const preview = get("preview") as Level | "";
  const reason = get("reason");
  const competitor = get("competitor");
  const offset = Number(get("offset") || 0);
  const brief = get("brief");
  const q = useApi<Review>(path("/review", { level: preview || undefined, reason, competitor, brief, limit: PAGE, offset }));
  const current = meta?.level;
  const shown = q.data?.level;
  const previewing = Boolean(preview && current && preview !== current);
  const [trustMsg, setTrustMsg] = useState<TrustResult | null>(null);

  return (
    <>
      <PageHead title="Review queue" sub="Items held by the routing rules, each with the reason it was held" />
      {brief ? <BriefScope brief={brief} applied={q.data ? q.data.scope?.brief === brief : null} onClear={() => set({ brief: null, offset: null })} /> : null}
      {trustMsg ? <TrustToast res={trustMsg} onDone={() => setTrustMsg(null)} /> : null}

      <Async {...q} retry={() => q.mutate()} rows={6}>
        {(r) => {
          const lv = r.levels.find((x) => x.level === r.level);
          return (
            <>
              <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))]">
                <Panel title="How much should the system decide alone?" cap={lv ? <>over non-noise items<N n={lv.n} /></> : undefined}>
                  <LevelControl levels={r.levels} current={current} shown={shown} onPreview={(l) => set({ preview: l === current ? null : l, offset: null })} />
                </Panel>
                <Panel title="How much needs a human?" cap={`at ${label(LEVEL_LABEL, r.level)}`}>
                  {lv ? (
                    <Donut center={lv.held} caption="held" parts={[
                      { label: "Held for review", value: lv.held, color: "#f59e0b" },
                      { label: "Published", value: lv.published, color: "#41be57" },
                    ]} />
                  ) : <Empty>No counts.</Empty>}
                </Panel>
                <Panel title="Why are items held?" cap="an item can count twice · click to filter">
                  {Object.keys(r.counts_by_reason).length ? (
                    <div className="flex flex-col">
                      {Object.entries(r.counts_by_reason).sort((a, b) => b[1] - a[1]).map(([code, n]) => (
                        <button key={code} type="button" onClick={() => set({ reason: reason === code ? null : code, offset: null })}
                          className={cn("rounded text-left hover:bg-page", reason === code && "bg-accent")}>
                          <HBars max={Math.max(...Object.values(r.counts_by_reason))} rows={[{ label: label(HOLD_LABEL, code), value: n, color: reason === code ? "var(--jgreen-d)" : undefined }]} />
                        </button>
                      ))}
                    </div>
                  ) : <Empty>Nothing is held at this level.</Empty>}
                </Panel>
              </div>

              {previewing ? (
                <PreviewBar preview={preview as Level} current={current!} onBack={() => set({ preview: null })} />
              ) : null}

              <TrustedSources />

              <Panel
                title="What needs my decision?"
                cap={`${r.total} held at ${label(LEVEL_LABEL, r.level)}${reason ? ` for ${label(HOLD_LABEL, reason)}` : ""} · held at every level first`}
                right={
                  <span className="flex flex-wrap gap-2">
                    <FilterSelect ariaLabel="Competitor" allLabel="All competitors" value={competitor} onChange={(v) => set({ competitor: v, offset: null })}
                      options={(meta?.competitors ?? []).map((c) => ({ value: c.key, label: c.name }))} />
                    <FilterSelect ariaLabel="Hold reason" allLabel="All reasons" value={reason} onChange={(v) => set({ reason: v, offset: null })}
                      options={(meta?.hold_reasons ?? []).map((c) => ({ value: c, label: label(HOLD_LABEL, c) }))} />
                  </span>
                }
              >
                {previewing ? <div className="mb-2 text-xs text-mute">Actions are off while previewing another level.</div> : null}
                {r.items.length ? (
                  r.items.map((row) =>
                    row.kind === "item" ? (
                      <QueueItem key={row.item.item_id} row={row} level={r.level} disabled={previewing} onTrusted={setTrustMsg} />
                    ) : (
                      <ChangeRow key={`c${row.change_id}`} row={row} disabled={previewing} />
                    ),
                  )
                ) : (
                  <Empty>{reason || competitor ? "Nothing held matches these filters." : `The queue is empty at ${label(LEVEL_LABEL, r.level)}.`}</Empty>
                )}
                {r.total > PAGE ? (
                  <div className="mt-2.5 flex items-center justify-end gap-2">
                    <span className="text-xs text-mute">{offset + 1}–{Math.min(offset + PAGE, r.total)} of {r.total}</span>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset === 0} onClick={() => set({ offset: String(Math.max(0, offset - PAGE)) })}>Previous</Button>
                    <Button variant="outline" size="sm" className="h-7 text-xs" disabled={offset + PAGE >= r.total} onClick={() => set({ offset: String(offset + PAGE) })}>Next</Button>
                  </div>
                ) : null}
              </Panel>
            </>
          );
        }}
      </Async>
    </>
  );
}

function LevelControl({ levels, current, shown, onPreview }: {
  levels: Review["levels"]; current: Level | undefined; shown: Level | undefined; onPreview: (l: Level) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5" role="radiogroup" aria-label="Autonomy level">
      {levels.map((l) => (
        <button key={l.level} type="button" role="radio" aria-checked={shown === l.level} onClick={() => onPreview(l.level)}
          className={cn("flex items-center gap-3 rounded border px-3 py-2 text-left transition-colors hover:border-jgreen",
            shown === l.level ? "border-jgreen bg-accent" : "border-line")}>
          <span className="flex-1">
            <span className="font-semibold">{label(LEVEL_LABEL, l.level)}</span>
            {current === l.level ? <Tag className="ml-2 bg-jgreen px-1.5 text-[11px] text-white">current</Tag> : null}
            <span className="block text-[11px] text-mute">{LEVEL_HELP[l.level]}</span>
          </span>
          <span className="text-right">
            <b className="text-lg font-semibold tabular-nums">{l.held}</b>
            <span className="block text-[11px] text-mute">held</span>
          </span>
        </button>
      ))}
    </div>
  );
}

function PreviewBar({ preview, current, onBack }: { preview: Level; current: Level; onBack: () => void }) {
  const refresh = useRefreshAll();
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const apply = async () => {
    setErr(null);
    try {
      await send("PUT", "/api/v1/settings/autonomy-level", { level: preview });
      setConfirm(false);
      onBack();
      await refresh();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-[#f59e0b] bg-[#fffaf0] px-4 py-2.5">
      <span className="flex-1">
        Previewing <b>{label(LEVEL_LABEL, preview)}</b>. Nothing has changed; the current level is still <b>{label(LEVEL_LABEL, current)}</b>.
      </span>
      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onBack}>Back to {label(LEVEL_LABEL, current)}</Button>
      <Button size="sm" className="h-7 text-xs" onClick={() => setConfirm(true)}>Set {label(LEVEL_LABEL, preview)} as the level</Button>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change the autonomy level to {label(LEVEL_LABEL, preview)}?</DialogTitle>
            <DialogDescription>
              Items held only for reasons that {label(LEVEL_LABEL, preview)} doesn&apos;t hold are published at once. Items an analyst already decided keep their decision.
            </DialogDescription>
          </DialogHeader>
          {err ? <ErrorNote error={err} /> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(false)}>Cancel</Button>
            <Button onClick={apply}>Set {label(LEVEL_LABEL, preview)}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ReasonChips({ reasons, level }: { reasons: HoldReason[]; level: Level }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {reasons.map((h) => {
        const always = h.held_at.length === 3;
        const active = h.held_at.includes(level);
        return (
          <span key={h.code} title={h.detail}
            className={cn("inline-flex items-center gap-1 rounded-[3px] border px-2 py-px text-xs",
              always ? "border-[#e5483b] bg-[#fff5f5] text-[#a32d2d]" : active ? "border-[#f59e0b] bg-[#fffaf0] text-[#8a5a00]" : "border-line text-mute")}>
            <b className="font-semibold">{label(HOLD_LABEL, h.code)}</b>
            <span>· {always ? "every level" : h.held_at.map((l) => LEVEL_LABEL[l] ?? l).join(", ")}</span>
          </span>
        );
      })}
    </div>
  );
}

function QueueItem({ row, level, disabled, onTrusted }: { row: ReviewItemRow; level: Level; disabled: boolean; onTrusted: (r: TrustResult) => void }) {
  const [err, setErr] = useState<ApiError | null>(null);
  const it = row.item;
  const ts = row.trust_source;
  const unvetted = it.hold_reasons.some((h) => h.code === "unvetted_source");
  return (
    <ItemRow
      item={it}
      showBadge={false}
      actions={<ItemActions item={it} disabled={disabled} onError={setErr} />}
      extra={
        <>
          <ReasonChips reasons={it.hold_reasons} level={level} />
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-mute">
            <span>Held since {fmtDateTime(row.held_since)}</span>
            {it.confidence != null ? <span>· confidence {it.confidence.toFixed(2)}</span> : null}
            {unvetted && ts && !ts.vetted ? (
              <TrustButton host={ts.host} fromItem={it.item_id} suggest={ts.suggest} approved={ts.approved} dismissed={ts.dismissed} disabled={disabled} onDone={onTrusted} onError={setErr} />
            ) : null}
          </div>
          {err ? <div className="mt-1.5"><ErrorNote error={err} /></div> : null}
        </>
      }
    />
  );
}

function TrustButton({ host, fromItem, suggest, approved, dismissed, disabled, onDone, onError }: {
  host: string; fromItem: string; suggest: boolean; approved: number; dismissed: number; disabled: boolean;
  onDone: (r: TrustResult) => void; onError: (e: ApiError | null) => void;
}) {
  const refresh = useRefreshAll();
  const [busy, setBusy] = useState(false);
  const trust = async () => {
    setBusy(true);
    onError(null);
    try {
      const res = await send<TrustResult>("POST", "/api/v1/sources/trust", { host, from_item_id: fromItem });
      onDone(res);
      await refresh();
    } catch (e) {
      onError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span>· {host}: {approved} approved, {dismissed} dismissed</span>
      <Button size="sm" variant="outline" className={cn("h-6 px-2 text-[11px]", suggest && "border-jgreen text-jgreen-d")} disabled={disabled || busy} onClick={trust}
        title="Add this host to the vetted list in the store; its items stop being held for an unvetted source">
        <ShieldCheck className="size-3" /> Trust this source{suggest ? " (suggested)" : ""}
      </Button>
    </span>
  );
}

function TrustToast({ res, onDone }: { res: TrustResult; onDone: () => void }) {
  const refresh = useRefreshAll();
  const [err, setErr] = useState<ApiError | null>(null);
  const undo = async () => {
    try {
      await send("DELETE", `/api/v1/sources/trust/${encodeURIComponent(res.host)}`);
      await refresh();
      onDone();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <div role="status" className="flex flex-wrap items-center gap-3 rounded-md border border-jgreen bg-[#f3fbf4] px-4 py-2.5">
      <ShieldCheck className="size-4 text-jgreen-d" />
      <span className="flex-1">
        <b>{res.host}</b> is now trusted. {res.released.total} item{res.released.total === 1 ? "" : "s"} released
        {res.still_held.total ? `, ${res.still_held.total} still held for another reason` : ""}.
      </span>
      {err ? <ErrorNote error={err} /> : null}
      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={undo}><Undo2 className="size-3" /> Undo</Button>
      <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onDone}>Close</Button>
    </div>
  );
}

/** Suggested hosts (3+ approvals, 0 dismissals) and the hosts trusted from this screen, with remove. */
function TrustedSources() {
  const refresh = useRefreshAll();
  const suggested = useApi<Page<SourceRow>>(path("/sources", { kind: "suggested", limit: 20 }));
  const vetted = useApi<Page<SourceRow>>(path("/sources", { kind: "vetted", limit: 200 }));
  const [err, setErr] = useState<ApiError | null>(null);
  const trusted = vetted.data?.items.filter((s) => s.group === "trusted") ?? [];
  const act = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <Panel title="Which sources have earned trust?" cap="Suggested after 3+ approvals and no dismissals">
      {err ? <div className="mb-2"><ErrorNote error={err} /></div> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-1 text-xs font-semibold text-mute">Suggested</h3>
          <Async {...suggested} retry={() => suggested.mutate()} rows={2} isEmpty={(d) => !d.items.length}
            empty="No host has 3+ approvals and 0 dismissals yet.">
            {(d) => d.items.map((s) => (
              <div key={s.host} className="flex items-center gap-2 border-t border-line py-1.5 first:border-t-0">
                <span className="flex-1">{s.host} <span className="text-xs text-mute">{s.approved} approved · {s.held} held</span></span>
                <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]" onClick={() => act(() => send("POST", "/api/v1/sources/trust", { host: s.host }))}>
                  <ShieldCheck className="size-3" /> Trust
                </Button>
              </div>
            ))}
          </Async>
        </div>
        <div>
          <h3 className="mb-1 text-xs font-semibold text-mute">Trusted from this screen</h3>
          <Async {...vetted} retry={() => vetted.mutate()} rows={2} isEmpty={() => !trusted.length}
            empty="None yet. Hosts from config/vetted_sources.yaml are managed in the repo.">
            {() => trusted.map((s) => (
              <div key={s.host} className="flex items-center gap-2 border-t border-line py-1.5 first:border-t-0">
                <span className="flex-1">{s.host}</span>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => act(() => send("DELETE", `/api/v1/sources/trust/${encodeURIComponent(s.host)}`))}>
                  <Undo2 className="size-3" /> Remove
                </Button>
              </div>
            ))}
          </Async>
        </div>
      </div>
    </Panel>
  );
}

const CHANGE_DISMISS: Record<string, string> = {
  wrong_extraction: "Wrong extraction",
  cosmetic: "Cosmetic change",
  not_a_change: "Not a change",
};

function ChangeRow({ row, disabled }: { row: ReviewChangeRow; disabled: boolean }) {
  const { data: meta } = useMeta();
  const refresh = useRefreshAll();
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(row.new_value ?? "");
  const id = encodeURIComponent(row.change_id);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      setEditing(false);
      await refresh();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const off = disabled || busy;
  return (
    <div className="flex items-start gap-3 border-t border-line bg-[#fff7e6] px-2.5 py-2.5 first:border-t-0">
      <Tag className="bg-[#f59e0b] text-white">Cell</Tag>
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{competitorName(meta, row.competitor)} · {row.axis_label ?? row.axis ?? "axis unknown"}: head-to-head cell changed</div>
        <div className="mt-1 grid gap-2 text-xs md:grid-cols-2">
          <div><div className="text-mute">Was</div>{row.old_value || "—"}{row.old_evidence ? <div className="mt-0.5 italic text-mute">&ldquo;{row.old_evidence}&rdquo;</div> : null}</div>
          <div><div className="text-mute">Now</div>{row.new_value || "—"}{row.new_evidence ? <div className="mt-0.5 italic text-mute">&ldquo;{row.new_evidence}&rdquo;</div> : null}</div>
        </div>
        {row.tier_changes?.length ? (
          <ul className="m-0 mt-1.5 list-none p-0 text-xs">
            {row.tier_changes.map((t, i) => (
              <li key={i}><b className="font-semibold">{t.tier}</b> {t.change}{t.old_name ? ` (was ${t.old_name})` : ""}: {t.old || "—"} → {t.new || "—"}</li>
            ))}
          </ul>
        ) : null}
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-mute">
          {row.held_since ? <span>Detected {fmtDateTime(row.held_since)}</span> : null}
          {row.page_url ? <ExtLink href={row.page_url}>tracked page</ExtLink> : null}
          <span>Held at every level</span>
        </div>
        {editing ? (
          <div className="mt-2 flex flex-col gap-1.5">
            <Textarea value={value} onChange={(e) => setValue(e.target.value)} rows={2} aria-label="Corrected cell value" className="bg-white" />
            <div className="flex gap-1.5">
              <Button size="sm" className="h-7 text-xs" disabled={off || !value.trim()} onClick={() => run(() => send("PATCH", `/api/v1/changes/${id}`, { value }))}>Save value</Button>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          </div>
        ) : null}
        {err ? <div className="mt-1.5"><ErrorNote error={err} /></div> : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
        <Button size="sm" variant="outline" className="h-7 border-jgreen px-2.5 text-xs text-jgreen-d hover:bg-jgreen hover:text-white" disabled={off}
          onClick={() => run(() => send("POST", `/api/v1/changes/${id}/approve`, {}))}>
          <Check className="size-3.5" /> Approve
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs" disabled={off}><X className="size-3.5" /> Dismiss <ChevronDown className="size-3" /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel className="text-xs text-mute">Dismiss restores the old value</DropdownMenuLabel>
            {Object.entries(CHANGE_DISMISS).map(([k, v]) => (
              <DropdownMenuItem key={k} onSelect={() => run(() => send("POST", `/api/v1/changes/${id}/dismiss`, { reason: k }))}>{v}</DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs" disabled={off} onClick={() => setEditing(true)}><Pencil className="size-3.5" /> Edit</Button>
      </div>
    </div>
  );
}

/** The queue scoped to one Brief window (from the Brief's "Review these"). Says so when the API ignores the filter. */
function BriefScope({ brief, applied, onClear }: { brief: string; applied: boolean | null; onClear: () => void }) {
  return (
    <div className="-mt-2 flex flex-wrap items-center gap-2 text-xs">
      <Tag className="bg-[#e8eefb] font-semibold text-[#3f5b8f]">Held from the Brief of {fmtLongDate(brief)}</Tag>
      {applied === false ? (
        <span className="text-[#8a5a00]">The API doesn&apos;t filter by Brief yet, so this is the whole backlog.</span>
      ) : null}
      <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={onClear}>Show the whole backlog</Button>
    </div>
  );
}
