"use client";
// D16 analyst actions on one item: Approve, Dismiss + reason, Edit, Flag. Each sends the item version (If-Match).
import { useState } from "react";
import { useSWRConfig } from "swr";
import { Check, ChevronDown, Flag, Pencil, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FilterSelect } from "@/components/FilterSelect";
import { ApiError, send } from "@/lib/api";
import { ErrorNote, FLAG_TIP } from "@/components/ci";
import { DISMISS_LABEL, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import type { Item } from "@/lib/types";

/** Refetch everything from the API after a write: queue, counts, Brief, Log all derive from the same store. */
export function useRefreshAll() {
  const { mutate } = useSWRConfig();
  return () => mutate((k) => typeof k === "string" && k.startsWith("/api/v1/"));
}

const btn = "h-7 px-2.5 text-xs";

const UNFLAG_TIP = "Removes the important mark. The item's status does not change.";

export function ItemActions({ item, disabled, onError, onApproved }: {
  item: Item; disabled?: boolean; onError: (e: ApiError | null) => void; onApproved?: (item: Item) => void;
}) {
  const refresh = useRefreshAll();
  const { data: meta } = useMeta();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const id = encodeURIComponent(item.item_id);

  const run = async (fn: () => Promise<unknown>, done?: () => void) => {
    setBusy(true);
    onError(null);
    try {
      await fn();
      done?.();
      await refresh();
    } catch (e) {
      onError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  const off = disabled || busy || item.status === "held_out";
  return (
    <>
      <Button size="sm" variant="outline" className={`${btn} border-jgreen text-jgreen-d hover:bg-jgreen hover:text-white`} disabled={off}
        onClick={() => run(() => send("POST", `/api/v1/items/${id}/approve`, {}, item.version), () => onApproved?.(item))}>
        <Check className="size-3.5" /> Approve
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="outline" className={btn} disabled={off}>
            <X className="size-3.5" /> Dismiss <ChevronDown className="size-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <div className="max-w-[17rem] px-2 py-1.5 text-xs text-[#44516a]">
            Dismiss removes the item from the feed. To fix the competitor, category or score, use Edit.
          </div>
          <DropdownMenuItem onSelect={() => setEditing(true)} className="font-semibold text-jgreen-d">
            <Pencil className="size-3.5" /> Edit the item instead…
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-xs text-mute">Dismiss because (names the stage that failed)</DropdownMenuLabel>
          {(meta?.dismiss_reasons ?? Object.keys(DISMISS_LABEL)).map((r) => (
            <DropdownMenuItem key={r} onSelect={() => run(() => send("POST", `/api/v1/items/${id}/dismiss`, { reason: r }, item.version))}>
              {label(DISMISS_LABEL, r)}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <Button size="sm" variant="outline" className={btn} disabled={off} onClick={() => setEditing(true)}>
        <Pencil className="size-3.5" /> Edit
      </Button>
      {/* D107: Flag only marks the item; it toggles with Unflag, and neither changes the item's status. A dismissed
          item is never offered Flag (the API answers 409); a dismissed flagged item gets UnflagButton instead */}
      {item.status === "dismissed" ? null : item.flagged ? (
        <Button size="sm" variant="outline" className={btn} disabled={off} title={UNFLAG_TIP} aria-pressed
          onClick={() => run(() => send("DELETE", `/api/v1/items/${id}/flag`, undefined, item.version))}>
          <Flag className="size-3.5 fill-current" /> Unflag
        </Button>
      ) : (
        <Button size="sm" variant="outline" className={btn} disabled={off} title={FLAG_TIP} aria-pressed={false}
          onClick={() => run(() => send("POST", `/api/v1/items/${id}/flag`, {}, item.version))}>
          <Flag className="size-3.5" /> Flag
        </Button>
      )}
      {editing ? (
        <EditDialog item={item} onClose={() => setEditing(false)}
          onSave={(body) => run(() => send("PATCH", `/api/v1/items/${id}`, body, item.version)).then(() => setEditing(false))} />
      ) : null}
    </>
  );
}

function EditDialog({ item, onClose, onSave }: { item: Item; onClose: () => void; onSave: (b: Record<string, unknown>) => void }) {
  const { data: meta } = useMeta();
  const [competitor, setCompetitor] = useState(item.competitor);
  const [category, setCategory] = useState(item.category ?? "");
  const [score, setScore] = useState(item.score ? String(item.score) : "");
  const [note, setNote] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const body: Record<string, unknown> = {};
  if (competitor && competitor !== item.competitor) body.competitor = competitor;
  if (category && category !== item.category) body.category = category;
  if (score && Number(score) !== item.score) body.score = Number(score);
  const changed = Object.keys(body).length > 0;
  // §13.2: a note only for a field this edit changes (any other gives 422); a field without one gets the shared note.
  const fieldNotes = Object.fromEntries(Object.keys(body).filter((f) => notes[f]?.trim()).map((f) => [f, notes[f].trim()]));
  const noteFor = (f: string) => (
    <FieldNote field={f} enabled={f in body} value={notes[f] ?? ""} onChange={(v) => setNotes({ ...notes, [f]: v })} />
  );
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit the labels</DialogTitle>
          <DialogDescription className="line-clamp-2">{item.title}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label>Competitor</Label>
            <FilterSelect ariaLabel="Competitor" allLabel="(unchanged)" value={competitor} onChange={(v) => setCompetitor(v || item.competitor)}
              options={(meta?.competitors ?? []).map((c) => ({ value: c.key, label: c.name }))} className="h-8 w-full bg-white" />
            {noteFor("competitor")}
          </div>
          <div className="grid gap-1">
            <Label>Category</Label>
            <FilterSelect ariaLabel="Category" allLabel="(unchanged)" value={category} onChange={(v) => setCategory(v || (item.category ?? ""))}
              options={(meta?.categories ?? []).map((c) => ({ value: c, label: c }))} className="h-8 w-full bg-white" />
            {noteFor("category")}
          </div>
          <div className="grid gap-1">
            <Label>Importance</Label>
            <FilterSelect ariaLabel="Importance" allLabel="(unchanged)" value={score} onChange={(v) => setScore(v || (item.score ? String(item.score) : ""))}
              options={[5, 4, 3, 2, 1].map((n) => ({ value: String(n), label: String(n) }))} className="h-8 w-full bg-white" />
            {noteFor("score")}
          </div>
          <div className="grid gap-1">
            <Label htmlFor="edit-note">Note for the whole edit (optional; used for any field without its own note)</Label>
            <Textarea id="edit-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
          </div>
          <p className="m-0 text-xs text-mute">Saved as a label candidate for the golden set; it is merged by hand, never automatically.</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={!changed} onClick={() => onSave({ ...body, ...(note.trim() ? { note: note.trim() } : {}), ...(Object.keys(fieldNotes).length ? { notes: fieldNotes } : {}) })}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FieldNote({ field, enabled, value, onChange }: { field: string; enabled: boolean; value: string; onChange: (v: string) => void }) {
  return (
    <input type="text" aria-label={`Note for ${field}`} value={enabled ? value : ""} disabled={!enabled} onChange={(e) => onChange(e.target.value)}
      placeholder={enabled ? "Why this change? (optional)" : "Change the value to add a note"}
      className="h-7 rounded border border-line bg-white px-2 text-xs placeholder:text-mute disabled:bg-[#f6f8fa]" />
  );
}

/** Unflag only, for a dismissed item that kept its flag (D107: Dismiss leaves the flag; Flag on a dismissed item is a 409,
 *  so it is never offered). Version is sent when known (If-Match); the Log has none, which the API allows. */
export function UnflagButton({ itemId, version }: { itemId: string; version?: number }) {
  const refresh = useRefreshAll();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      await send("DELETE", `/api/v1/items/${encodeURIComponent(itemId)}/flag`, undefined, version);
      await refresh();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex flex-col gap-1">
      <Button size="sm" variant="outline" className={btn} disabled={busy} title={UNFLAG_TIP} aria-pressed data-unflag-only
        onClick={(e) => { e.stopPropagation(); void go(); }}>
        <Flag className="size-3.5 fill-current" /> Unflag
      </Button>
      {err ? <ErrorNote error={err} /> : null}
    </span>
  );
}

/** Re-open a dismissed item (§13.1), after a short confirm. It goes back to the status it had before the dismiss;
 * the dismiss stays in its history. Version is sent when known (If-Match); the Log has none, which the API allows. */
export function ReopenButton({ itemId, version, title }: { itemId: string; version?: number; title?: string }) {
  const refresh = useRefreshAll();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const confirm = async () => {
    setBusy(true);
    setErr(null);
    try {
      await send("POST", `/api/v1/items/${encodeURIComponent(itemId)}/reopen`, note.trim() ? { note: note.trim() } : {}, version);
      await refresh();
      setOpen(false);
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button size="sm" variant="outline" className={btn} onClick={(e) => { e.stopPropagation(); setOpen(true); }}>
        <RotateCcw className="size-3.5" /> Re-open
      </Button>
      {open ? (
        <Dialog open onOpenChange={(o) => !o && setOpen(false)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Re-open this item?</DialogTitle>
              <DialogDescription>
                {title ? <span className="mb-1 block line-clamp-2 font-medium text-ink">{title}</span> : null}
                It goes back to the status it had before it was dismissed. The dismiss stays in its history.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-1">
              <Label htmlFor="reopen-note">Note (optional)</Label>
              <Textarea id="reopen-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
            </div>
            {err ? <ErrorNote error={err} /> : null}
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button disabled={busy} onClick={confirm}>Re-open</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );
}
