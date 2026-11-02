// One colour and one letter per competitor, used on every screen (avatars, heatmap columns, legends).
// No imports, so `npm test` runs this file directly. Company logos are never fetched or embedded.

/** The six tracked competitors, plus Industry. Colours are distinct from each other and readable with white text. */
export const COMPETITOR_COLOR: Record<string, string> = {
  cloudsmith: "#2563eb", // blue
  sonatype: "#be185d", // magenta
  github: "#1f2937", // near-black
  gitlab: "#7c3aed", // violet
  snyk: "#0f766e", // teal
  aws: "#b45309", // amber-brown
  industry: "#6b7280", // grey
};
export const OTHER_COLOR = "#9ca3af";

export function competitorColor(key: string | null | undefined): string {
  return (key && COMPETITOR_COLOR[key]) || OTHER_COLOR;
}

/** The first letter of the display name: GitHub → G, AWS → A. */
export function monogram(name: string | null | undefined, key?: string | null): string {
  const s = (name || key || "").trim();
  const m = s.match(/[A-Za-z0-9]/);
  return m ? m[0].toUpperCase() : "?";
}
