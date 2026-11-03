// Hold-reason chips in the Review queue. A reason held at every autonomy level reads "Always reviewed: …" with a plain
// hover; its meaning is the one ci/route.py gives it. Other reasons keep their label, their levels and the API's detail.
// No imports, so `npm test` runs it.

export interface HoldReasonLike { code: string; detail?: string | null; held_at: string[] }
export interface HoldChip { label: string; levels: string | null; hint: string }

const LEVELS: Record<string, string> = { strict: "Strict", balanced: "Balanced", relaxed: "Relaxed" };
const WHATEVER = "whatever the autonomy setting (Strict, Balanced or Relaxed).";

/** Every-level reasons: [label after "Always reviewed: ", who always goes to an analyst]. */
export const ALWAYS_REVIEWED: Record<string, [string, string]> = {
  mentions_jfrog: ["mentions JFrog", "Items that mention JFrog always go"],
  pricing: ["pricing", "Pricing & Packaging items always go"],
  m_and_a: ["M&A / funding", "Funding, M&A and partnership items always go"],
  model_failure: ["model failure", "Items the AI model gave no usable answer for always go"],
  invalid_output: ["invalid model output", "Items whose AI model output failed the checks always go"],
  changed_cell: ["changed head-to-head cell", "Every changed head-to-head cell always goes"],
};

export function alwaysReviewedHint(code: string, label: string): string {
  const who = ALWAYS_REVIEWED[code]?.[1] ?? `Items held for "${label}" always go`;
  return `${who} to an analyst, ${WHATEVER}`;
}

export function holdChip(h: HoldReasonLike, label: string): HoldChip {
  const always = Object.keys(LEVELS).every((l) => h.held_at.includes(l));
  if (always) {
    const name = ALWAYS_REVIEWED[h.code]?.[0] ?? label.charAt(0).toLowerCase() + label.slice(1);
    return { label: `Always reviewed: ${name}`, levels: null, hint: alwaysReviewedHint(h.code, label) };
  }
  return { label, levels: h.held_at.map((l) => LEVELS[l] ?? l).join(", "), hint: h.detail ?? "" };
}
