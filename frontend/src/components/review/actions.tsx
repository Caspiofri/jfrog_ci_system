"use client";
// D16 analyst actions on one item: Approve, Dismiss + reason, Edit, Flag. Each sends the item version (If-Match).
import { useState } from "react";
import { useSWRConfig } from "swr";
import { Check, ChevronDown, Flag, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FilterSelect } from "@/components/FilterSelect";
import { ApiError, send } from "@/lib/api";
import { DISMISS_LABEL, label } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import type { Item } from "@/lib/types";

/** Refetch everything from the API after a write: queue, counts, Brief, Log all derive from the same store. */
export function useRefreshAll() {
  const { mutate } = useSWRConfig();
  return () => mutate((k) => typeof k === "string" && k.startsWith("/api/v1/"));
}

const btn = "h-7 px-2.5 text-xs";

export function ItemActions({ item, disabled, onError }: { item: Item; disabled?: boolean; onError: (e: ApiError | null) => void }) {
  const refresh = useRefreshAll();
  const { data: meta } = useMeta();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const id = encodeURIComponent(item.item_id);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    onError(null);
    try {
      await fn();
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
        onClick={() => run(() => send("POST", `/api/v1/items/${id}/approve`, {}, item.version))}>
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
      <Button size="sm" variant="outline" className={btn} disabled={off} title="Mark as important; a flag on a low score is a ranking miss"
        onClick={() => run(() => send("POST", `/api/v1/items/${id}/flag`, {}, item.version))}>
        <Flag className="size-3.5" /> Flag
      </Button>
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
  const body: Record<string, unknown> = {};
  if (competitor && competitor !== item.competitor) body.competitor = competitor;
  if (category && category !== item.category) body.category = category;
  if (score && Number(score) !== item.score) body.score = Number(score);
  const changed = Object.keys(body).length > 0;
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
          </div>
          <div className="grid gap-1">
            <Label>Category</Label>
            <FilterSelect ariaLabel="Category" allLabel="(unchanged)" value={category} onChange={(v) => setCategory(v || (item.category ?? ""))}
              options={(meta?.categories ?? []).map((c) => ({ value: c, label: c }))} className="h-8 w-full bg-white" />
          </div>
          <div className="grid gap-1">
            <Label>Importance</Label>
            <FilterSelect ariaLabel="Importance" allLabel="(unchanged)" value={score} onChange={(v) => setScore(v || (item.score ? String(item.score) : ""))}
              options={[5, 4, 3, 2, 1].map((n) => ({ value: String(n), label: String(n) }))} className="h-8 w-full bg-white" />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="edit-note">Note (optional)</Label>
            <Textarea id="edit-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
          </div>
          <p className="m-0 text-xs text-mute">Saved as a label candidate for the golden set; it is merged by hand, never automatically.</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={!changed} onClick={() => onSave({ ...body, ...(note ? { note } : {}) })}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
