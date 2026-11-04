// The insights section title (D113): "Cumulative insights" for any window the generator used (insights.window.days).
// ci/insights.py: 7 days by default, widened to 14 when 7 days hold fewer than 15 stories; the (i) hover gives the exact
// window. No imports.
export const INSIGHTS_TITLE_HINT = "Patterns across the last 7 to 14 days, not only this Brief.";

export function insightsTitle(window: { days?: number } | null | undefined): string {
  const d = Number(window?.days);
  if (!Number.isFinite(d) || d <= 0) return "Insights";
  return "Cumulative insights";
}
