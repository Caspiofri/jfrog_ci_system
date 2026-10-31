// After a production build: fail if any mock-mode code or fixture reached the bundle. Usage: node scripts/no-mock-in-bundle.mjs <distDir>
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const dist = process.argv[2] || ".next";
const MARKERS = ["text-basis.local", "Dev mock mode", "mock_insights", "SAMPLE_LENS", "14-day hold)"];
const hits = [];
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(js|html|rsc|json)$/.test(name)) {
      const text = readFileSync(p, "utf8");
      for (const m of MARKERS) if (text.includes(m)) hits.push(`${p}: ${m}`);
    }
  }
}
for (const sub of ["static", "server/app"]) {
  try { walk(join(dist, sub)); } catch { /* absent in some builds */ }
}
if (hits.length) {
  console.error(`Mock-mode code found in the production bundle (${dist}):\n${hits.join("\n")}`);
  process.exit(1);
}
console.log(`No mock-mode code in ${dist}.`);
