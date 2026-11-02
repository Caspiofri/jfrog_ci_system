// npm test: one AI label (sparkles) on the insights, newspaper next to "Daily Brief", each with its hover (mouse and focus).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const brief = read("app/brief/page.tsx");
const shell = read("components/shell/Shell.tsx");
const ci = read("components/ci.tsx");

test("insights: one AI label with sparkles, the visible text and the exact hover; no Experimental, no flask", () => {
  assert.match(brief, /const AI_LABEL = "AI-generated — check the cited sources";/);
  assert.match(brief, /const AI_HINT =\s*"AI-written summary that connects several stories\. Checked on a small sample \(1 Nov: 4 insights, 12 claims\): facts were well supported \(11 of 12 claims\), but some conclusions were stronger than the evidence\. Open the cited sources before sharing\.";/);
  assert.match(brief, /function AiLabel[\s\S]*?<Hint text=\{AI_HINT\}>[\s\S]*?<Sparkles[\s\S]*?\{AI_LABEL\}/);
  assert.equal((brief.match(/<Sparkles\b/g) ?? []).length, 2, "the insights label, plus the AI mark on a claim's JFrog comparison line");
  assert.equal((brief.match(/<AiLabel \/>/g) ?? []).length, 1, "one AI label");
  for (const f of ["app/brief/page.tsx", "components/health/parts.tsx", "components/ci.tsx"]) {
    const s = read(f).replace(/\/\/.*|\/\*[\s\S]*?\*\//g, "");
    assert.doesNotMatch(s, /Experimental|FlaskConical/, f);
  }
});

test("Daily Brief: newspaper icon, exact hover, name unchanged", () => {
  assert.match(brief, /const DAILY_BRIEF_HINT = "Everything new since the previous Brief, ranked by importance\.";/);
  assert.match(brief, /title="Daily Brief"\s*icon=\{<Newspaper[^}]*\}\s*titleHint=\{DAILY_BRIEF_HINT\}/);
  assert.match(shell, /label: "Daily Brief", icon: Newspaper/);
});

test("icons come from the library already in use", () => {
  assert.match(brief, /import \{[^}]*\bNewspaper\b[^}]*\bSparkles\b[^}]*\} from "lucide-react"/);
});

test("the title hover is reachable by keyboard", () => {
  assert.match(ci, /\{titleHint \? <Hint text=\{titleHint\}>\{title\}<\/Hint> : title\}/);
  assert.match(ci, /export function Hint[\s\S]*?tabIndex=\{0\}/);
});

test("the Brief's window range is still available, on the date", () => {
  assert.match(brief, /<Hint text=\{brief\.data\?\.window \? \(backfill[\s\S]*?Everything discovered from/);
});
