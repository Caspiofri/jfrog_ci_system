// Bold numbers, currency amounts and "+" signs in a value, for display only: the pieces join back to the exact
// text, and dates (ISO dates, years, "Mar 2026", "Sept 30") stay plain. No imports, so `npm test` runs it.

export interface Piece { text: string; bold: boolean }

const MONTH = "(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\\.?";
// dates first, so their digits are never bolded
const DATE = new RegExp(`\\b\\d{4}-\\d{2}-\\d{2}\\b|\\b${MONTH}\\s+\\d{1,2}(?:,\\s*\\d{4})?\\b|\\b${MONTH}\\s+\\d{4}\\b|\\b(?:19|20)\\d{2}\\b`, "g");
// currency amounts ($1,200 / €0.5 / USD 10), numbers with an optional +, %, or x, and lone "+"
const NUM = /(?:[$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP)\b|\b\d[\d,]*(?:\.\d+)?\+?%?|\+\d[\d,]*(?:\.\d+)?%?|(?<=\s|^)\+(?=\s|$))/g;

export function emphasize(text: string): Piece[] {
  const marks: [number, number, boolean][] = []; // [start, end, bold]
  const taken = new Array(text.length).fill(false);
  for (const m of text.matchAll(DATE)) for (let i = m.index!; i < m.index! + m[0].length; i++) taken[i] = true;
  for (const m of text.matchAll(NUM)) {
    const s = m.index!, e = s + m[0].length;
    if (taken.slice(s, e).some(Boolean)) continue;
    marks.push([s, e, true]);
  }
  const out: Piece[] = [];
  let at = 0;
  for (const [s, e] of marks) {
    if (s > at) out.push({ text: text.slice(at, s), bold: false });
    out.push({ text: text.slice(s, e), bold: true });
    at = e;
  }
  if (at < text.length) out.push({ text: text.slice(at), bold: false });
  return out;
}
