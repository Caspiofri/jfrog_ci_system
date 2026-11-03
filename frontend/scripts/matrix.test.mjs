// npm test: "JFrog vs competitors" matrix (src/lib/matrix.ts, components/competitors/Matrix.tsx).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { NOT_FOUND, SHORT_MAX, STATE_INFO, STATE_ORDER, anyMark, buildMatrix, capabilityCount, capabilityRows, matrixCell, shortWords, shorten, stateTotals } from "../src/lib/matrix.ts";

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

// ---- capability-first view (D75) ----
const ORDER = ["cloudsmith", "sonatype", "github", "gitlab", "snyk", "aws"];
const sixProfiles = (over = {}) => ORDER.map((k) => profile(k, over[k] ?? {}));

test("left column counts 'n of 7 pages state something' from the cells: value and stale count, the rest don't", () => {
  const rows = buildMatrix(sixProfiles({
    snyk: { ai_mcp: cell({ state: "not_stated", value: "" }) },
    aws: { ai_mcp: cell({ state: "not_tracked", value: null }) },
    cloudsmith: { ai_mcp: cell({ state: "stale", value: "old" }) },
  }));
  const ai = rows.find((r) => r.axis === "ai_mcp");
  assert.deepEqual(capabilityCount(ai), { n: 5, of: 7 }); // JFrog + 4 competitors (one stale)
  assert.deepEqual(capabilityCount(rows[0]), { n: 7, of: 7 });
});

test("rows for one capability: JFrog first, then competitors that state something; the others fold into two name lists", () => {
  const rows = buildMatrix(sixProfiles({ snyk: { ai_mcp: cell({ state: "not_stated", value: "" }) }, aws: { ai_mcp: cell({ state: "not_tracked", value: null }) } }));
  const v = capabilityRows(rows.find((r) => r.axis === "ai_mcp"), ORDER);
  assert.equal(v.jfrog.short, "JFrog ai_mcp");
  assert.deepEqual(v.listed, ["cloudsmith", "sonatype", "github", "gitlab"]);
  assert.deepEqual(v.notStated, ["snyk"]);
  assert.deepEqual(v.notTracked, ["aws"]);
});

test("totals add up: 42 competitor cells, 49 with JFrog, on data shaped like 1 Nov", () => {
  const over = {
    cloudsmith: { package_coverage: cell({ state: "stale", value: "34 formats" }), pricing_model: cell({ state: "not_tracked", value: null }) },
    snyk: { package_coverage: cell({ state: "not_stated", value: "" }), curation_gating: cell({ state: "not_tracked", value: null }), ai_mcp: cell({ state: "not_stated", value: "" }) },
    aws: { security_scanning: cell({ state: "not_tracked", value: null }), ai_mcp: cell({ state: "not_tracked", value: null }), cicd_integration: cell({ state: "not_stated", value: "" }) },
  };
  const { comp, all } = stateTotals(buildMatrix(sixProfiles(over)));
  assert.deepEqual(comp, { value: 34, stale: 1, not_tracked: 4, not_stated: 3 });
  assert.equal(Object.values(comp).reduce((a, b) => a + b, 0), 42);
  assert.equal(Object.values(all).reduce((a, b) => a + b, 0), 49);
});

test("the view: capability list (select on narrow screens), first one open, Expand all, caption, no grid", () => {
  assert.match(comp, /const \[sel, setSel\] = useState\(0\)/);
  assert.match(comp, /role="tablist" aria-label="Capabilities"/);
  assert.match(comp, /<select value=\{sel\}/);
  assert.match(comp, /md:hidden/);
  assert.match(comp, /\{all \? "Show one capability" : "Expand all"\}/);
  assert.match(comp, /CAPTION = "What was found on public pages, not a verdict\."/);
  assert.doesNotMatch(comp, /<table|overflow-x-auto|StateIcon/);
});

test("vendor row: bold name beside every avatar (JFrog too), value ~70 characters wide and 2 lines, as-of right, Source icon, compare arrow on hover", () => {
  assert.match(comp, /<CompetitorAvatar k=\{k\} name=\{name\} size="md" \/>\s*\{name\}/);
  assert.match(comp, /flex w-36 shrink-0 items-center gap-1\.5 font-semibold/);
  assert.match(comp, /aria-expanded=\{open\}[\s\S]*?max-w-\[70ch\][\s\S]*?font-normal[\s\S]*?!open && "line-clamp-2"/);
  assert.match(comp, /sm:ml-auto sm:justify-end[\s\S]*?as of \{fmtDate\(c\.asOf, true\)\}/);
  assert.match(comp, /<ArticleLink href=\{c\.source\} label=\{`Open \$\{name\}'s source page in a new tab`\} iconOnly \/>/);
  assert.match(comp, /<Clock className="size-3" aria-hidden \/> Stale/);
  assert.match(comp, /href=\{`\/competitors\/\$\{encodeURIComponent\(k\)\}#head-to-head`\}[\s\S]*?opacity-0[\s\S]*?group-hover:opacity-100 \[@media\(hover:none\)\]:opacity-100/);
  assert.match(readFileSync(new URL("../src/app/competitors/[key]/page.tsx", import.meta.url), "utf8"), /id="head-to-head"/);
  assert.match(comp, /NOT_STATED_LINE = "Their page says nothing:"/);
  assert.match(comp, /NOT_TRACKED_LINE = "Not tracked yet:"/);
  const ci = readFileSync(new URL("../src/components/ci.tsx", import.meta.url), "utf8");
  assert.match(ci, /title=\{name \? `\$\{name\} · \$\{aria\}` : iconOnly \? "Source" : aria\}/);
});

test("JFrog row is the anchor: own-colour avatar, green tint and edge, then a 'Competitors' separator", async () => {
  const { COMPETITOR_COLOR } = await import("../src/lib/competitors.ts");
  assert.equal(COMPETITOR_COLOR.jfrog, "#1f7a33");
  assert.match(comp, /jfrog \? "border-l-4 border-jgreen bg-\[#eef7f0\]"/);
  assert.match(comp, /<VendorRow c=\{v\.jfrog\} k="jfrog" name="JFrog" jfrog \/>\s*<div[^>]*data-separator>\s*Competitors/);
});

test("capability list: selected is tinted with an accent bar and bold; others muted; one dot per vendor by data state", () => {
  assert.match(comp, /i === sel \? "border-jgreen border-l-4 bg-\[#eef7f0\] text-ink" : "border-line text-mute"/);
  assert.match(comp, /i === sel \? "font-bold" : "font-medium"/);
  assert.match(comp, /\{c\.n\} of \{c\.of\} pages state something<\/span>\s*<VendorDots /);
  assert.match(comp, /background: on \? competitorColor\(k\) : "#d5dbe4"/);
  assert.match(comp, /const label = `\$\{n\}: \$\{c \? STATE_INFO\[c\.state\]\.label/);
});

test("still at the top of the Competitors view, above the cards; JFrog row first with a light tint", () => {
  assert.ok(page.indexOf("<CapabilityMatrix />") < page.indexOf("<Async"));
  assert.match(comp, /<VendorRow c=\{v\.jfrog\} k="jfrog" name="JFrog" jfrog \/>[\s\S]*?\{v\.listed\.map/);
});

test("the title's (i) says it is a direct comparison of JFrog's capabilities with the competitors'", () => {
  assert.match(comp, /<Panel title="JFrog vs competitors" info=\{MATRIX_INFO\}/);
  assert.match(comp, /MATRIX_INFO = "A direct comparison of JFrog's capabilities with each competitor's, one capability at a time, from each vendor's public pages\.";/);
});
