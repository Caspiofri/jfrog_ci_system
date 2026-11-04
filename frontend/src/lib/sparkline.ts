// D93/D94: the 14-day line in each competitor card, from GET /competitors/{key} activity (by article date, cleared
// items only: the API's PUBLISHED statuses). Display only: no score, trend or new measure. No imports, so `npm test` runs it.

export const SPARK_DAYS = 14;
export const SPARK_TITLE = "Cleared Items per Day · Last 14 Days";
export const SPARK_CAPTION = "By article date. Items that passed routing or were approved.";
/** Shown once above the competitor cards (D112), not inside each card. */
export const SPARK_LINE = `Sparklines: ${SPARK_CAPTION.charAt(0).toLowerCase()}${SPARK_CAPTION.slice(1)}`;

export interface DayRow { date: string; items: number }

/** The 14 days up to and including the Brief date, oldest first; a day the API didn't list counts 0. */
export function lastDays(series: DayRow[], briefDate: string, days = SPARK_DAYS): DayRow[] {
  const by = new Map(series.map((r) => [r.date, r.items]));
  const end = Date.parse(`${briefDate}T00:00:00Z`);
  if (Number.isNaN(end)) return [];
  const out: DayRow[] = [];
  for (let n = days - 1; n >= 0; n--) {
    const d = new Date(end - n * 86_400_000).toISOString().slice(0, 10);
    out.push({ date: d, items: by.get(d) ?? 0 });
  }
  return out;
}
