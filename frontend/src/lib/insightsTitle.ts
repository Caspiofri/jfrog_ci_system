// The insights section title, from the window the generator actually used for this Brief (insights.window.days).
// ci/insights.py: 7 days by default, widened to 14 when 7 days hold fewer than 15 stories. No imports.
export function insightsTitle(window: { days?: number } | null | undefined): string {
  const d = Number(window?.days);
  if (!Number.isFinite(d) || d <= 0) return "Insights";
  return d === 7 ? "Weekly insights" : `Insights · last ${d} days`;
}
