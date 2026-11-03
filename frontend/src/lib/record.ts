// One record loaded by id (an item, a competitor, a run, a Brief date): show it only when its id is the requested
// one. A response for another id (the previous record kept by the fetch layer, or a slow earlier request that
// arrives after a fast switch) is never shown, and a failed load shows the error, never the previous record.
// No imports, so `npm test` runs it.
export function pickRecord<T>(requested: string | null | undefined, data: T | undefined, idOf: (d: T) => string | null | undefined): T | undefined {
  if (data === undefined || data === null || !requested) return undefined;
  return idOf(data) === requested ? data : undefined;
}

/** True while a response is on hand but belongs to another id: actions must stay disabled. */
export function isStale<T>(requested: string | null | undefined, data: T | undefined, idOf: (d: T) => string | null | undefined): boolean {
  return data !== undefined && data !== null && Boolean(requested) && idOf(data) !== requested;
}
