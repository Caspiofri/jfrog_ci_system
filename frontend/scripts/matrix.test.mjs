// npm test: "JFrog vs competitors" matrix (src/lib/matrix.ts, components/competitors/Matrix.tsx).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { NOT_FOUND, SHORT_MAX, STATE_INFO, STATE_ORDER, anyMark, buildMatrix, matrixCell, shortWords, shorten } from "../src/lib/matrix.ts";

const AXES = [["deployment", "Deployment"], ["package_coverage", "Package coverage"], ["security_scanning", "Security scanning"],
  ["curation_gating", "Curation/gating"], ["ai_mcp", "AI & MCP"], ["cicd_integration", "CI/CD integration"], ["pricing_model", "Pricing model"]];
const cell = (o = {}) => ({ state: "value", value: "v", source_url: "https://example.com/pricing", as_of: "2026-10-30T11:57:03Z", change: null, ...o });
const JF = (axis) => cell({ value: `JFrog ${axis}`, source_url: "https://jfrog.com/pricing/" });
const profile = (key, over = {}) => ({
  key, axes: AXES.map(([axis, label]) => ({ axis, label, jfrog: JF(axis), competitor: over[axis] ?? cell({ value: `${key} ${axis}` }), changed: false })),
});

test("rows: the 7 capabilities in the API's order and names", () => {
  const rows = buildMatrix([profile("github"), profile("snyk")]);
  assert.deepEqual(rows.map((r) => r.label), AXES.map((a) => a[1]));
});

test("full cell: the value, its source and date; JFrog's own cell in its column", () => {
  const [r] = buildMatrix([profile("github")]);
  assert.equal(r.jfrog.text, "JFrog deployment");
  assert.equal(r.jfrog.source, "https://jfrog.com/pricing/");
  const c = r.cells.github;
  assert.deepEqual([c.text, c.full, c.empty, c.source, c.asOf], ["github deployment", "github deployment", false, "https://example.com/pricing", "2026-10-30T11:57:03Z"]);
});

test("long values are shortened for the cell; the hover keeps the full text", () => {
  const long = "Supports 34 package formats including Alpine, Cargo, Conan, Dart, Debian, Docker, Go, Helm, Hex, Maven, npm, NuGet, PyPI and more";
  const c = matrixCell(cell({ value: long }));
  assert.ok(c.text.length <= SHORT_MAX && c.text.endsWith("…"));
  assert.equal(c.full, long);
  assert.equal(shorten("short"), "short");
});

test("empty cells say 'Not found yet' with the reason, never a guess", () => {
  const cases = [
    [cell({ state: "not_stated", value: "" }), /says nothing/],
    [cell({ state: "not_tracked", value: null, source_url: undefined, as_of: undefined, reason: "no security page" }), /No public page is tracked.*no security page/],
    [null, /No head-to-head data/],
    [cell({ value: "   " }), /No value was extracted/],
  ];
  for (const [c, why] of cases) {
    const m = matrixCell(c);
    assert.equal(m.text, NOT_FOUND);
    assert.equal(m.full, null);
    assert.equal(m.empty, true);
    assert.match(m.why, why);
  }
});

test("a competitor with no head-to-head at all: every cell is 'Not found yet'", () => {
  const rows = buildMatrix([profile("github"), { key: "aws", axes: null }]);
  assert.ok(rows.every((r) => r.cells.aws.text === NOT_FOUND));
});

test("stale keeps the value and marks it; changed shows only when change detection marked the cell", () => {
  const s = matrixCell(cell({ state: "stale", value: "old text", stale_reason: "page fetch failed" }));
  assert.deepEqual([s.text, s.stale, s.staleReason], ["old text", true, "page fetch failed"]);
  const ch = matrixCell(cell({ change: { change_id: "c1", old_value: "a", new_value: "b", tier_changes: [], detected_at: "2026-11-01T04:02:00Z", status: "awaiting_review" } }));
  assert.equal(ch.changedAt, "2026-11-01T04:02:00Z");
  const rows = buildMatrix([profile("github")]);
  assert.equal(anyMark(rows, "changedAt"), false, "no change anywhere: nothing extra");
  assert.equal(anyMark(buildMatrix([profile("github", { ai_mcp: cell({ change: { detected_at: "2026-11-01" } }) })]), "changedAt"), true);
});

const comp = readFileSync(new URL("../src/components/competitors/Matrix.tsx", import.meta.url), "utf8");
const lib = readFileSync(new URL("../src/lib/matrix.ts", import.meta.url), "utf8");
const page = readFileSync(new URL("../src/app/competitors/page.tsx", import.meta.url), "utf8");

test("hover and keyboard focus show the state, full text, source and date", () => {
  assert.match(comp, /<Hint text=\{<CellHint/);
  assert.match(comp, /\{STATE_INFO\[c\.state\]\.label\}/);
  assert.match(comp, /\{c\.full \? <span>\{c\.full\}<\/span>/);
  assert.match(comp, /Source: \{host\(c\.source\)\}/);
  assert.match(comp, /as of \$\{fmtDate\(c\.asOf, true\)\}/);
  assert.match(comp, /<ArticleLink href=\{c\.source\}/);
});

test("columns: JFrog first, then the six tracked competitors with avatars, not Industry", () => {
  assert.match(comp, /Capability<\/th>\s*<th[^>]*>JFrog<\/th>/);
  assert.match(comp, /!c\.is_industry && c\.key !== "industry"/);
  assert.match(comp, /<CompetitorAvatar k=\{p\.key\}/);
});

test("title, caption, legend; at the top of the Competitors view, above the cards", () => {
  assert.match(comp, /title="JFrog vs competitors"/);
  assert.match(comp, /export const CAPTION = "Colour shows what we found on each competitor's public pages, not a verdict on their product\.";/);
  assert.match(comp, /data-caption>\{CAPTION\}/);
  assert.doesNotMatch(comp, /Capabilities from public sources/);
  assert.match(comp, /data-legend/);
  assert.ok(page.indexOf("<CapabilityMatrix />") > -1 && page.indexOf("<CapabilityMatrix />") < page.indexOf("<CompetitorCardView"));
  assert.ok(page.indexOf("<CapabilityMatrix />") < page.indexOf("<Async"), "above everything else on the page");
});

test("narrow screens: the matrix scrolls by itself, first column sticky", () => {
  assert.match(comp, /<div className="overflow-x-auto" data-matrix>/);
  assert.match(comp, /sticky left-0/);
});

test("no verdicts: no gap, threat, ahead, behind or lens relation in the matrix", () => {
  const visible = (s) => s.replace(/\/\/.*|\/\*[\s\S]*?\*\//g, "").replace(/className=("[^"]*"|\{[^}]*\})/g, "");
  for (const s of [comp, lib]) assert.doesNotMatch(visible(s), /\bgap\b|threat|ahead|behind|relation|closes_gap|opens_gap/i);
});

test("four data states, each with its own icon, colour and label, from the API's state only", () => {
  assert.deepEqual(STATE_ORDER, ["value", "stale", "not_stated", "not_tracked"]);
  assert.deepEqual(STATE_ORDER.map((k) => [STATE_INFO[k].icon, STATE_INFO[k].label]),
    [["check", "Found"], ["clock", "Stale"], ["question", "Page says nothing"], ["dash", "Not tracked yet"]]);
  assert.equal(new Set(STATE_ORDER.map((k) => STATE_INFO[k].bg)).size, 4, "four colours");
  assert.equal(new Set(STATE_ORDER.map((k) => STATE_INFO[k].icon)).size, 4, "four icons");
  for (const k of STATE_ORDER) assert.ok(STATE_INFO[k].label.split(" ").length <= 3);
});

test("each state maps to its cell: value and stale keep a few words of the value, the others their label", () => {
  const long = "Supports npm, Maven, PyPI, RubyGems, and NuGet repositories with upstream proxying";
  const v = matrixCell(cell({ value: long }));
  assert.deepEqual([v.state, v.short, v.full], ["value", "Supports npm, Maven, PyPI…", long]);
  const st = matrixCell(cell({ state: "stale", value: "Supports 34 package formats" }));
  assert.deepEqual([st.state, st.short], ["stale", "Supports 34 package formats"]);
  const ns = matrixCell(cell({ state: "not_stated", value: "" }));
  assert.deepEqual([ns.state, ns.short, ns.full], ["not_stated", "Page says nothing", null]);
  const nt = matrixCell(cell({ state: "not_tracked", value: null, source_url: undefined }));
  assert.deepEqual([nt.state, nt.short, nt.source], ["not_tracked", "Not tracked yet", null]);
  assert.equal(matrixCell(null).state, "not_tracked");
  assert.ok(shortWords("one two three four five six").split(" ").length <= 4);
});

test("JFrog's column uses the same cell: the check icon with its own short value", () => {
  const [r] = buildMatrix([profile("github")]);
  assert.deepEqual([r.jfrog.state, r.jfrog.short], ["value", "JFrog deployment"]);
  assert.match(comp, /<MatrixTd c=\{r\.jfrog\} who="JFrog"/);
});

test("icon and colour always together; the legend lists the four states with both", () => {
  assert.match(comp, /<td[^>]*style=\{\{ background: st\.bg \}\}[\s\S]*?<StateIcon state=\{c\.state\} \/>/);
  assert.match(comp, /STATE_ORDER\.map\(\(k\) => \([\s\S]*?<StateIcon state=\{k\} \/>[\s\S]*?\{STATE_INFO\[k\]\.label\}/);
  assert.match(comp, /role="img" aria-label=\{s\.label\}/);
});

test("no cell text, label, legend or caption says present, absent, partial, gap, threat, ahead or behind", () => {
  const banned = /\b(present|absent|partial|gap|threat|ahead|behind)\b/i;
  for (const k of STATE_ORDER) assert.doesNotMatch(STATE_INFO[k].label, banned);
  const visible = comp.replace(/\/\/.*|\/\*[\s\S]*?\*\//g, "").replace(/className=("[^"]*"|\{[^}]*\})/g, "");
  assert.doesNotMatch(visible, banned);
  for (const c of [cell(), cell({ state: "stale" }), cell({ state: "not_stated", value: "" }), null]) {
    const m = matrixCell(c);
    assert.doesNotMatch(`${m.short} ${m.why ?? ""}`, banned);
  }
});
