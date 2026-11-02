// The header above the competitor cards: totals of what the six competitors' cards count (GET /competitors),
// summed in the UI. The Industry card (market news with no tracked competitor) is not a competitor and is left out.
// No imports, so `npm test` runs it.
export function cardTotals(cards: { items_7d: number; pending_review: number; is_industry?: boolean }[]) {
  const comp = cards.filter((c) => !c.is_industry);
  return {
    published: comp.reduce((t, c) => t + (c.items_7d ?? 0), 0),
    queued: comp.reduce((t, c) => t + (c.pending_review ?? 0), 0),
  };
}
