"use client";
// A letter monogram in the competitor's colour (no company logos), and the avatar with its name.
import { competitorColor, monogram } from "@/lib/competitors";
import { competitorName, useMeta } from "@/lib/meta";
import { cn } from "@/lib/utils";

export function CompetitorAvatar({ k, name, size = "sm", className }: { k: string | null | undefined; name?: string; size?: "sm" | "md" | "lg"; className?: string }) {
  const { data: meta } = useMeta();
  if (!k || k === "none") return null;
  const n = name ?? competitorName(meta, k);
  return (
    <span role="img" aria-label={n} title={n} data-avatar={k}
      className={cn("inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold leading-none text-white",
        size === "sm" ? "size-4 text-[0.5625rem]" : size === "md" ? "size-6 text-[0.6875rem]" : "size-8 text-sm", className)}
      style={{ background: competitorColor(k) }}>
      {monogram(n, k)}
    </span>
  );
}

/** Avatar and name together: the name always sits next to the letter, so G (GitHub) and G (GitLab) can't be confused. */
export function CompetitorLabel({ k, className }: { k: string | null | undefined; className?: string }) {
  const { data: meta } = useMeta();
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <CompetitorAvatar k={k} />
      <span>{competitorName(meta, k)}</span>
    </span>
  );
}
