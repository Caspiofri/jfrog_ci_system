"use client";
// The JFrog lens on the item card and in the item drawer. Collected and model text renders as React text only (D32).
import Link from "next/link";
import { AXIS_LABEL } from "@/lib/format";
import type { Lens, LensStatus } from "@/lib/types";

/** "Why it matters to JFrog" (D58): the closest JFrog capability only. The relation and the lens sentence are not
 * shown: the 1 Nov check found the relation wrong where it was claimed, while the axis and quote held up. */
export function LensView({ lens: l, status }: { lens?: Lens | null; status?: LensStatus | null }) {
  if (!l) {
    const unavailable = status === "rejected" || status === "failed";
    return <span className="text-mute">{unavailable ? "Analysis unavailable" : "Not analyzed yet"}</span>;
  }
  if (l.relation === "not_related" || !l.capability_quote) {
    return <span className="text-mute">No direct link to a JFrog capability</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      <span>
        <span className="text-xs text-mute">Closest JFrog capability: </span>
        {l.axis ? (
          <Link href={`/capabilities#${encodeURIComponent(l.axis)}`} className="font-medium text-jgreen-d hover:underline">
            {AXIS_LABEL[l.axis] ?? l.axis}
          </Link>
        ) : <span className="font-medium">—</span>}
      </span>
      <blockquote className="m-0 border-l-2 border-jgreen pl-2 text-xs text-mute">
        <span className="italic">&ldquo;{l.capability_quote}&rdquo;</span>
        <span className="not-italic"> — JFrog capability sheet</span>
      </blockquote>
    </div>
  );
}
