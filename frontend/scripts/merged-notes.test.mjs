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
  assert.match(r, /state !== "ok" && "invisible"/); // keeps its place while loading; gone if the image fails
  assert.match(r, /onLoad=\{\(\) => setState\("ok"\)\} onError=\{\(\) => setState\("none"\)\}/);
  assert.match(r, /const CONCEPT_LABEL = "Concept, sample data";/);
  assert.match(r, /<figcaption[^>]*data-concept-label>\{CONCEPT_LABEL\}<\/figcaption>\s*\{\/\*[^*]*\*\/\}\s*<div [^>]*data-shot-frame>\s*<Image /); // against the image, in its frame
  assert.doesNotMatch(r, /object-cover|Screenshot to add/); // shown whole, never cropped; no placeholder
  assert.match(r, /loading="eager"/); // a lazy image inside the hidden frame would never load
  assert.match(r, /className="flex h-\[18rem\] items-center justify-center p-2" data-shot-frame/); // one fixed frame height
  assert.match(r, /className="block h-auto max-h-full w-auto max-w-full"/); // whole and centred, never cropped, stretched or enlarged
  assert.match(r, /className="grid gap-x-3\.5 gap-y-3\.5 md:grid-cols-2" data-roadmap-grid/); // 2 per row, 1 on narrow screens
  assert.match(r, /"row-span-4 grid grid-rows-subgrid /); // title, image and both lines line up across a row
  assert.match(r, /c\.wide && "md:col-span-2"/);
  assert.equal((r.match(/!c\.wide && "md:min-h-\[2lh\]"/g) ?? []).length, 2); // equal half-card heights
  assert.deepEqual([...r.matchAll(/slug: "([^"]+)",\s*wide: true/g)].map((m) => m[1]), ["topics", "reactions"]);
});

test("Roadmap (D104): the seven concepts, in Ofri's order and words; the six images are the prototype's, unedited", () => {
  const r = src("app/roadmap/page.tsx");
  const slugs = [...r.matchAll(/slug: "([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(slugs, ["strength-radar", "convergence", "topics", "reactions", "pressure", "emerging", "deal-extraction"]);
  assert.match(r, /shows: "a competitor's strength against JFrog on each of the 7 axes, scored 1 to 5\.",\s*missing: "a strength score per axis, set or checked by a product expert\.",/);
  assert.match(r, /missing: "extraction of buyer, target and deal type\. The product's real deals block lists items as they are\.",/);
  for (const f of ["strength-radar", "convergence", "topics", "reactions", "pressure", "emerging", "deal-extraction"]) {
    assert.ok(readFileSync(new URL(`../public/roadmap/${f}.png`, import.meta.url)).length > 1000, f);
  }
});

test("demo mode only: the snapshot line under the header, dated from the manifest (GET /meta)", () => {
  const shell = src("components/shell/Shell.tsx");
  assert.match(shell, /const d = data\?\.meta\.mode === "demo" \? data\.meta\.snapshot\?\.date : null;\s*if \(!d\) return null;/);
  assert.match(shell, /Demo snapshot of \{fmtDate\(d, true\)\}\. The live system keeps running daily at 06:00\./);
  assert.match(shell, /<\/header>\s*<DemoLine \/>/);
});

test("D107: Flag toggles with Unflag, with the hover as written; one Flagged badge in Review, the drawer and the Log", () => {
  const a = src("components/review/actions.tsx");
  assert.match(a, /item\.flagged \? \([\s\S]*?send\("DELETE", `\/api\/v1\/items\/\$\{id\}\/flag`[\s\S]*?Unflag[\s\S]*?\) : \([\s\S]*?title=\{FLAG_TIP\}[\s\S]*?send\("POST", `\/api\/v1\/items\/\$\{id\}\/flag`/);
  assert.match(src("components/ci.tsx"), /export const FLAG_TIP = "Marks this item as important\. It does not approve or publish it\.";/);
  assert.match(src("components/ItemRow.tsx"), /\{item\.flagged \? <FlaggedBadge \/> : null\}/);
  assert.match(src("components/ItemDrawer.tsx"), /\{it\.flagged \? <FlaggedBadge \/> : null\}/);
  assert.match(src("app/log/page.tsx"), /\{r\.flagged \? <FlaggedBadge \/> : null\}/);
});

test("D107: a dismissed flagged item is offered Unflag only; Flag is never offered on a dismissed item", () => {
  const a = src("components/review/actions.tsx");
  assert.match(a, /\{item\.status === "dismissed" \? null : item\.flagged \? \(/);
  assert.match(a, /export function UnflagButton[\s\S]*?send\("DELETE", `\/api\/v1\/items\/\$\{encodeURIComponent\(itemId\)\}\/flag`/);
  const unflagOnly = a.slice(a.indexOf("export function UnflagButton"), a.indexOf("export function ReopenButton"));
  assert.doesNotMatch(unflagOnly, /"POST"/);
  assert.match(src("app/log/page.tsx"), /r\.status === "dismissed" && r\.item_id \? \([\s\S]*?\{r\.flagged \? <UnflagButton itemId=\{r\.item_id\} \/> : null\}/);
  assert.match(src("components/ItemDrawer.tsx"), /it\.status === "dismissed" \? \([\s\S]*?\{it\.flagged \? <UnflagButton itemId=\{it\.item_id\} version=\{it\.version\} \/> : null\}/);
  assert.match(src("app/review/page.tsx"), /\{it\.status === "dismissed" && it\.flagged \? <UnflagButton itemId=\{it\.item_id\} version=\{it\.version\} \/> : null\}/);
});
