// npm test: insights' JFrog link: the capability of each claim's JFrog quote, and the "Touches JFrog" chip.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { CAPABILITY_NAME, CAPABILITY_ORDER, claimCapability, insightCapabilities, parseSheet } from "../src/lib/capabilitySheet.ts";
import { CAPABILITY_ROWS } from "../src/lib/capabilityRows.ts";

const SHEET = readFileSync(new URL("../../config/jfrog_capabilities.md", import.meta.url), "utf8");
// the two JFrog quotes the 31 Oct insights carry (the only ones in any Brief so far)
const FIREWALL = '"Package firewall": blocks malicious, vulnerable, license-violating and immature packages';
const MCP = "approved MCP servers for Claude Code, Cursor, VS Code.";

test("the browser's copy of the sheet rows equals config/jfrog_capabilities.md (rerun the generator if not)", () => {
  assert.deepEqual(CAPABILITY_ROWS, parseSheet(SHEET));
  assert.deepEqual(CAPABILITY_ROWS.map((r) => r.key).sort(), [...CAPABILITY_ORDER].sort());
});

test("stored field: the claim's own capability wins", () => {
  assert.deepEqual(claimCapability({ jfrog_quote: MCP, jfrog_axis: "deployment" }, CAPABILITY_ROWS), { key: "deployment", source: "stored" });
  assert.deepEqual(claimCapability({ jfrog_quote: "", axis: "pricing_model" }, CAPABILITY_ROWS), { key: "pricing_model", source: "stored" });
});

test("exact match: the one sheet row that contains the quote", () => {
  assert.deepEqual(claimCapability({ jfrog_quote: FIREWALL }, CAPABILITY_ROWS), { key: "curation_gating", source: "exact_match" });
  assert.deepEqual(claimCapability({ jfrog_quote: MCP }, CAPABILITY_ROWS), { key: "ai_mcp", source: "exact_match" });
});

test("none: no quote, no exact match (case or spacing differs), or a quote found in more than one row; never a guess", () => {
  for (const q of ["", undefined, "APPROVED MCP SERVERS for Claude Code, Cursor, VS Code.", "approved  MCP servers", "blocks malicious packages everywhere"]) {
    assert.deepEqual(claimCapability({ jfrog_quote: q }, CAPABILITY_ROWS), { key: null, source: "none" });
  }
  const rows = [{ key: "deployment", text: "SaaS and self-hosted" }, { key: "pricing_model", text: "SaaS and self-hosted tiers" }];
  assert.deepEqual(claimCapability({ jfrog_quote: "SaaS and self-hosted" }, rows), { key: null, source: "none" });
  assert.deepEqual(claimCapability({ jfrog_quote: MCP, axis: "not_a_capability" }, CAPABILITY_ROWS), { key: "ai_mcp", source: "exact_match" });
});

test("Touches JFrog: distinct capabilities in the order of the 7; none when no claim has one", () => {
  const claims = [{ jfrog_quote: MCP }, { jfrog_quote: FIREWALL }, { jfrog_quote: MCP }, { jfrog_quote: "" }];
  assert.deepEqual(insightCapabilities(claims, CAPABILITY_ROWS), ["curation_gating", "ai_mcp"]);
  assert.deepEqual(insightCapabilities([{ jfrog_quote: "" }, {}], CAPABILITY_ROWS), []);
  assert.equal(CAPABILITY_NAME.curation_gating, "Curation/gating");
});

const brief = readFileSync(new URL("../src/app/brief/page.tsx", import.meta.url), "utf8");

test("the claim shows 'JFrog <capability>:' before the quote, or the quote credited to the sheet", () => {
  assert.match(brief, /JFrog \{CAPABILITY_NAME\[cap\.key\]\}:<\/b> <span className="italic">&ldquo;\{c\.jfrog_quote\}&rdquo;/);
  assert.match(brief, /&ldquo;\{c\.jfrog_quote\}&rdquo;<\/span> — JFrog capability sheet/);
});

test("the chip is in the header, visible while collapsed", () => {
  const card = brief.slice(brief.indexOf("function InsightCard("), brief.indexOf("function ExperimentalChip") > 0 ? brief.indexOf("function ExperimentalChip") : brief.indexOf("function AiLabel"));
  const collapsed = card.slice(card.indexOf("return ("), card.indexOf("{details ? ("));
  assert.match(collapsed, /<TouchesJfrog claims=\{ins\.claims\} \/>/);
  assert.match(brief, /Touches JFrog: \{caps\.map\(\(k\) => CAPABILITY_NAME\[k\]\)\.join\(" · "\)\}/);
});
