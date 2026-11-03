// npm test: Ofri's notes on the merged system (display only).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("Refresh insights sits under the insights, never in demo mode, and says why when no model is configured", () => {
  const brief = src("app/brief/page.tsx");
  const panel = brief.slice(brief.indexOf("function InsightsPanel"), brief.indexOf("function windowText"));
  assert.doesNotMatch(panel, /right=\{\s*<Button/);
  assert.match(panel, /\{demo \? null : \([\s\S]*?data-refresh[\s\S]*?Refresh insights[\s\S]*?<\/Panel>/);
  assert.match(panel, /err\?\.code === "llm_unavailable" \?[\s\S]*?\{REFRESH_UNAVAILABLE\}/);
  assert.match(brief, /const REFRESH_UNAVAILABLE = "Refresh needs a configured model, so it is not available here\.";/);
  for (const f of ["app/review/page.tsx", "app/health/page.tsx", "app/competitors/page.tsx", "app/log/page.tsx"]) assert.doesNotMatch(src(f), /Refresh insights|insights\/refresh/, f);
});

test("JFrog vs competitors: a value is a button (hover colour, pointer) only when 2 lines cut it off", () => {
  const m = src("components/competitors/Matrix.tsx");
  assert.match(m, /\{cut \|\| open \? \(\s*<button[\s\S]*?data-expandable/);
  assert.match(m, /<span ref=\{\(el\) => \{ ref\.current = el; \}\} className="line-clamp-2 [^"]*">/);
  const plain = m.slice(m.indexOf("<span ref="), m.indexOf("</span>", m.indexOf("<span ref=")));
  assert.doesNotMatch(plain, /hover:|cursor-pointer/);
});

test("Health: one accuracy panel when both blocks read the same report, two labelled panels otherwise", () => {
  const h = src("app/health/page.tsx");
  assert.match(h, /e\.report === t\.report && e\.created_at === t\.created_at/);
  assert.match(h, /\{sameEvalReport\(h\) \? \(\s*\/\/[^\n]*\n\s*<Panel title="How accurate is the system\? · Held-out test split"/);
  assert.match(h, /title=\{`Newest eval run · \$\{h\.eval\?\.split \?\? "unknown"\} split`\} cap="Not the reported numbers/);
  assert.doesNotMatch(h, /What does the held-out test split say\?/);
});

test("Roadmap: a slot appears only when its image loads; labelled; no placeholder or file path on screen", () => {
  const r = src("app/roadmap/page.tsx");
  assert.match(r, /if \(state === "none"\) return null;/);
  assert.match(r, /state !== "ok" && "hidden"/);
  assert.match(r, /onLoad=\{\(\) => setState\("ok"\)\} onError=\{\(\) => setState\("none"\)\}/);
  assert.match(r, />Concept, sample data</);
  assert.doesNotMatch(r, /Screenshot to add/);
});
