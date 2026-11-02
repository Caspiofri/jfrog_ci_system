// npm test: flask next to "Experimental", newspaper next to "Daily Brief", each with its hover (mouse and focus).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const brief = read("app/brief/page.tsx");
const shell = read("components/shell/Shell.tsx");
const ci = read("components/ci.tsx");

test("Experimental: flask icon and the exact hover text", () => {
  assert.match(brief, /const EXPERIMENTAL_HINT =\s*"AI-written summaries across several stories\. Facts were checked on 1 Nov \(11 of 12 claims supported\), but conclusions can be overstated\. Check the cited sources before sharing\.";/);
  assert.match(brief, /function ExperimentalChip[\s\S]*?<Hint text=\{EXPERIMENTAL_HINT\}>[\s\S]*?<FlaskConical[\s\S]*?Experimental/);
});

test("Daily Brief: newspaper icon, exact hover, name unchanged", () => {
  assert.match(brief, /const DAILY_BRIEF_HINT = "Everything new since the previous Brief, ranked by importance\.";/);
  assert.match(brief, /title="Daily Brief"\s*icon=\{<Newspaper[^}]*\}\s*titleHint=\{DAILY_BRIEF_HINT\}/);
  assert.match(shell, /label: "Daily Brief", icon: Newspaper/);
});

test("icons come from the library already in use", () => {
  assert.match(brief, /import \{[^}]*\bFlaskConical\b[^}]*\bNewspaper\b[^}]*\} from "lucide-react"/);
});

test("the title hover is reachable by keyboard", () => {
  assert.match(ci, /\{titleHint \? <Hint text=\{titleHint\}>\{title\}<\/Hint> : title\}/);
  assert.match(ci, /export function Hint[\s\S]*?tabIndex=\{0\}/);
});

test("the Brief's window range is still available, on the date", () => {
  assert.match(brief, /<Hint text=\{brief\.data\?\.window \? \(backfill[\s\S]*?Everything discovered from/);
});
