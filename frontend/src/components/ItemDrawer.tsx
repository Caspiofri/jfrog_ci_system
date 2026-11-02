"use client";
// The item drawer: GET /api/v1/items/{id}. Opened from any screen with useItemDrawer().open(id).
import { ArticleExcerpt } from "@/components/ArticleExcerpt";
import { MentionsJfrog } from "@/components/MentionsJfrog";
import { mentionExplanation, showLensBlock } from "@/lib/jfrogMention";
import { CompetitorLabel } from "@/components/CompetitorAvatar";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ArticleLink, Async, CategoryTag, ScoreBadge, StatusDot, Tag } from "@/components/ci";
import { LensView } from "@/components/LensView";
import { ReopenButton } from "@/components/review/actions";
import { useRecord } from "@/lib/api";
import { HOLD_LABEL, LEVEL_LABEL, SOURCE_LABEL, STATUS_LABEL, fmtDate, fmtDateTime, fmtPublished, label } from "@/lib/format";
import { competitorName, useMeta } from "@/lib/meta";
import type { FieldChange, ItemAction, ItemDetail, Lens, LensStatus, Meta } from "@/lib/types";

const Ctx = createContext<{ open: (id: string) => void }>({ open: () => {} });
export const useItemDrawer = () => useContext(Ctx);

export function ItemDrawerProvider({ children }: { children: ReactNode }) {
  const [id, setId] = useState<string | null>(null);
  const open = useCallback((x: string) => setId(x), []);
  const value = useMemo(() => ({ open }), [open]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <Sheet open={id !== null} onOpenChange={(o) => !o && setId(null)}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
          {id ? <DrawerBody id={id} /> : null}
        </SheetContent>
      </Sheet>
    </Ctx.Provider>
  );
}

function Field({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-2 border-t border-line py-2 first:border-t-0">
      <span className="text-mute">{k}</span>
      <span className="min-w-0 break-words">{children}</span>
    </div>
  );
}

/** The JFrog lens as the card shows it (D58): the closest capability only, no relation or lens sentence. */
function LensBlock({ lens, status }: { lens?: Lens | null; status?: LensStatus | null }) {
  return (
    <div className="rounded border-l-4 border-jgreen bg-[#f8fbf8] px-3 py-2">
      <div className="mb-1 text-xs font-semibold text-mute">Why it matters to JFrog</div>
      <LensView lens={lens} status={status} />
    </div>
  );
}

/** Why the item is tagged "Mentions JFrog": how the tag is set, the sentence when the excerpt holds it, what the tag
 *  changed, and the model's note when it names JFrog. Only fields the API serves; nothing is guessed. */
function MentionWhy({ d }: { d: ItemDetail }) {
  const m = mentionExplanation(d);
  if (!m) return null;
  return (
    <div className="flex flex-col gap-1 rounded-sm border-l-2 border-jgreen bg-[#eef7f0] px-2.5 py-1.5 text-xs text-jgreen-d" data-jfrog-mention>
      <b className="font-semibold">Why &ldquo;Mentions JFrog&rdquo;</b>
      <span className="text-ink">{m.how}</span>
      {m.sentence ? <span className="italic">&ldquo;{m.sentence}&rdquo;</span> : null}
      {m.effect.map((e) => <span key={e} className="text-ink">{e}</span>)}
      {m.modelNote ? <span className="text-ink"><span className="text-mute">The model&apos;s note: </span>{m.modelNote}</span> : null}
    </div>
  );
}

function DrawerBody({ id }: { id: string }) {
  const { data: meta } = useMeta();
  // only the requested item, never the previous one (a 404 or a slow earlier response shows an error or loading)
  const q = useRecord<ItemDetail>(`/api/v1/items/${encodeURIComponent(id)}`, id, (d) => d.item?.item_id);
  return (
    <>
      <SheetHeader className="px-5 pt-5 pb-0">
        <SheetTitle className="flex items-start gap-1.5 pr-6 text-base leading-snug">
          <span>{q.data?.item.title ?? "Item"}</span>
          {q.data ? <ArticleLink href={q.data.item.url} className="mt-1" /> : null}
        </SheetTitle>
        <SheetDescription className="text-xs">Item {id}</SheetDescription>
      </SheetHeader>
      <div className="px-5 pb-6">
        <Async {...q} retry={() => q.mutate()} rows={6}>
          {(d) => {
            const it = d.item;
            return (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  <ScoreBadge score={it.score} noise={it.noise} />
                  <StatusDot status={it.status} />
                  <CategoryTag category={it.category} />
                  {it.mentions_jfrog ? <MentionsJfrog excerpt={it.excerpt} /> : null}
                  {it.flagged ? <Tag className="bg-[#fdeaea] text-[#a32d2d]">Flagged</Tag> : null}
                  {it.status === "dismissed" ? <span className="ml-auto"><ReopenButton itemId={it.item_id} version={it.version} title={it.title} /></span> : null}
                </div>
                {showLensBlock(it.lens, it.lens_status) ? <LensBlock lens={it.lens} status={it.lens_status} /> : null}
                <MentionWhy d={d} />
                <ArticleExcerpt excerpt={it.excerpt} url={it.url} />
                <div>
                  <Field k="Competitor"><CompetitorLabel k={it.competitor} />{!it.classified ? " (prefilled, not classified)" : ""}</Field>
                  <Field k="Publisher">{it.publisher} · {label(SOURCE_LABEL, it.source)}</Field>
                  {it.scheduled_for ? (
                    <Field k="Feed date">{fmtDate(it.scheduled_for, true)} (scheduled, after we collected it)</Field>
                  ) : (
                    <Field k="Feed date">
                      {it.published_at_source ? (
                        <>{fmtDate(it.published_at_source, true)}<span className="text-mute"> · later than when we collected it ({fmtDate(it.published_at, true)})</span></>
                      ) : fmtPublished(it.published_at, it.date_precision)}
                    </Field>
                  )}
                  <Field k="Discovered">{fmtDateTime(it.discovered_at)}{it.discovery_lag_hours != null ? ` (${Math.round(it.discovery_lag_hours)} h after the feed date)` : ""}</Field>
                  <Field k="Score reason">{it.reason || "—"}</Field>
                  {it.why_it_matters ? <Field k="Ranker's summary">{it.why_it_matters}</Field> : null}
                  {d.ranking?.raw_score != null && d.ranking.raw_score !== it.score ? <Field k="Model score">{d.ranking.raw_score} (adjusted to {it.score ?? "—"})</Field> : null}
                  <Field k="Classified by">{d.classification?.method ?? "—"}{d.classification?.reason ? ` · ${d.classification.reason}` : ""}</Field>
                  <Field k="Confidence">{it.confidence != null ? it.confidence.toFixed(2) : "—"}</Field>
                  {d.skip ? <Field k="Held out">{d.skip}</Field> : null}
                  {d.rejections.length ? <Field k="Rejected output">{d.rejections.join("; ")}</Field> : null}
                </div>
                {it.hold_reasons.length ? (
                  <div>
                    <h3 className="mb-1 text-sm font-semibold">Hold reasons</h3>
                    <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                      {it.hold_reasons.map((r) => (
                        <li key={r.code}>
                          <b className="font-semibold">{label(HOLD_LABEL, r.code)}</b>
                          <span className="text-mute"> · held at {r.held_at.map((l) => LEVEL_LABEL[l] ?? l).join(", ")}</span>
                          <div className="text-xs text-mute">{r.detail}</div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <div>
                  <h3 className="mb-1 text-sm font-semibold">History</h3>
                  {d.sightings.map((s) => (
                    <div key={s.run_id} className="text-xs text-mute">Seen in run {s.run_id}{s.seen_at ? ` · ${fmtDateTime(s.seen_at)}` : ""}</div>
                  ))}
                  {d.actions.map((a, i) => <ActionLine key={i} a={a} meta={meta} />)}
                  {!d.actions.length ? <div className="text-xs text-mute">No analyst actions yet.</div> : null}
                </div>
              </div>
            );
          }}
        </Async>
      </div>
    </>
  );
}

const FIELD_LABEL: Record<string, string> = { competitor: "Competitor", category: "Category", score: "Importance" };

function fieldValue(meta: Meta | undefined, c: FieldChange, v: FieldChange["old"]) {
  if (v === null || v === undefined || v === "") return "—";
  return c.field === "competitor" ? competitorName(meta, String(v)) : String(v);
}

/** One analyst action in the drawer's history. An edit lists old -> new per field with its note (§13.2);
 * a re-open names the status it returned to (§13.1). */
function ActionLine({ a, meta }: { a: ItemAction; meta: Meta | undefined }) {
  const changes = a.payload?.changes ?? [];
  const back = a.action === "reopen" && a.payload?.status_before_dismiss ? ` → back to ${label(STATUS_LABEL, a.payload.status_before_dismiss)}` : "";
  return (
    <div className="text-xs">
      {fmtDateTime(a.at)} · <b>{a.action}</b>{a.reason ? ` (${a.reason})` : ""}{back}{a.note && !changes.length ? `: ${a.note}` : ""}
      {changes.length ? (
        <ul className="m-0 mt-0.5 list-none pl-3">
          {changes.map((c) => (
            <li key={c.field}>
              {FIELD_LABEL[c.field] ?? c.field}: {fieldValue(meta, c, c.old)} → <b className="font-semibold">{fieldValue(meta, c, c.new)}</b>
              {c.note ? <span className="text-mute"> · {c.note}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
