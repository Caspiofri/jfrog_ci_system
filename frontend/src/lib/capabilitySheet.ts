// The JFrog capability sheet's "Capabilities by axis" rows (config/jfrog_capabilities.md), used to name the
// capability a claim's JFrog quote comes from. Exact string match only: a quote found in no row, or in more
// than one, gets no name (never a guess). No model call. No imports, so `npm test` runs it.

/** The 7 capabilities in the API's order, with the names the head-to-head data uses. */
export const CAPABILITY_ORDER = ["deployment", "package_coverage", "security_scanning", "curation_gating", "ai_mcp", "cicd_integration", "pricing_model"];
export const CAPABILITY_NAME: Record<string, string> = {
  deployment: "Deployment", package_coverage: "Package coverage", security_scanning: "Security scanning",
  curation_gating: "Curation/gating", ai_mcp: "AI & MCP", cicd_integration: "CI/CD integration", pricing_model: "Pricing model",
};

// the sheet's axis labels -> the API's keys (as ci/lens.py SHEET_AXES and the capabilities page)
const SHEET_AXES: Record<string, string> = {
  deployment: "deployment", "package coverage": "package_coverage", "security scanning": "security_scanning",
  "curation / gating": "curation_gating", "ai & mcp": "ai_mcp", "ci/cd integration": "cicd_integration", "pricing model": "pricing_model",
};

export interface SheetRow { key: string; text: string }

/** Markdown escapes and bold off, as the capabilities page shows the sheet; nothing else changes. */
const plain = (s: string) => s.replace(/\\(.)/g, "$1").replace(/\*\*/g, "").trim();

/** The axis rows of the sheet: the row's cells after the axis name, joined as shown. */
export function parseSheet(markdown: string): SheetRow[] {
  const rows: SheetRow[] = [];
  for (const line of markdown.split("\n")) {
    const cells = line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
    const key = SHEET_AXES[cells[0]?.toLowerCase()];
    if (key && cells.length >= 3 && !rows.some((r) => r.key === key)) rows.push({ key, text: cells.slice(1).map(plain).join(" | ") });
  }
  return rows;
}

export type CapabilitySource = "stored" | "exact_match" | "none";

/** The capability of one claim's JFrog quote: the claim's own field if it stores one, else the single sheet row
 *  that contains the quote exactly, else none. */
export function claimCapability(claim: { jfrog_quote?: string | null; axis?: string | null; jfrog_axis?: string | null },
  rows: SheetRow[]): { key: string | null; source: CapabilitySource } {
  const stored = claim.jfrog_axis ?? claim.axis;
  if (stored && CAPABILITY_NAME[stored]) return { key: stored, source: "stored" };
  const q = (claim.jfrog_quote ?? "").trim();
  if (!q) return { key: null, source: "none" };
  const hits = rows.filter((r) => r.text.includes(q));
  return hits.length === 1 ? { key: hits[0].key, source: "exact_match" } : { key: null, source: "none" };
}

/** The distinct capabilities an insight's claims touch, in the order of the 7 capabilities. */
export function insightCapabilities(claims: Parameters<typeof claimCapability>[0][], rows: SheetRow[]): string[] {
  const found = new Set(claims.map((c) => claimCapability(c, rows).key).filter((k): k is string => Boolean(k)));
  return CAPABILITY_ORDER.filter((k) => found.has(k));
}
