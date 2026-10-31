// The JFrog capability sheet's "Capabilities by axis" table, one anchored row per axis, so a lens quote links to
// the exact row it was checked against. Source: config/jfrog_capabilities.md, the committed copy the lens and
// insights quote checks read (byte-identical to docs/specs/JFrog capabilities.md, which is gitignored and so has no
// repo link). Read on the server at build time; rendered as plain text.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { PageHead, Panel } from "@/components/ci";

export const dynamic = "force-static";

const SHEET = join(process.cwd(), "..", "config", "jfrog_capabilities.md");

// The sheet's axis labels -> the API's axis keys (as ci/lens.py SHEET_AXES).
const SHEET_AXES: Record<string, string> = {
  deployment: "deployment",
  "package coverage": "package_coverage",
  "security scanning": "security_scanning",
  "curation / gating": "curation_gating",
  "ai & mcp": "ai_mcp",
  "ci/cd integration": "cicd_integration",
  "pricing model": "pricing_model",
};

/** Markdown escapes and emphasis off; the sheet's text is shown as written. */
const plain = (s: string) => s.replace(/\\(.)/g, "$1").replace(/\*\*/g, "").trim();

function readSheet() {
  const text = readFileSync(SHEET, "utf8");
  const rows: { key: string; axis: string; offers: string; tier: string }[] = [];
  for (const line of text.split("\n")) {
    const cells = line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
    const key = SHEET_AXES[cells[0]?.toLowerCase()];
    if (key && cells.length >= 3) rows.push({ key, axis: cells[0], offers: plain(cells[1]), tier: plain(cells[2]) });
  }
  const verified = text.match(/\*\*Last verified:\*\*([^\n]*)/)?.[1];
  return { rows, verified: verified ? plain(verified) : null };
}

export default function CapabilitiesPage() {
  const { rows, verified } = readSheet();
  return (
    <>
      <PageHead title="JFrog capability sheet" sub="What JFrog offers on each head-to-head axis: the lines lens quotes are checked against" />
      <Panel title="Capabilities by axis" cap="config/jfrog_capabilities.md · official JFrog pages, as of 30 Oct 2026">
        {verified ? <p className="m-0 mb-3 text-xs text-mute">{verified}</p> : null}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr>
                {["Axis", "What JFrog offers", "Tier / add-on"].map((h) => (
                  <th key={h} className="border-b border-line px-2.5 py-2 text-left text-xs font-semibold text-mute">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} id={r.key} className="scroll-mt-20 target:bg-[#fff7e6] target:outline target:outline-2 target:outline-[#f59e0b]">
                  <td className="w-[10rem] border-b border-line px-2.5 py-2.5 align-top font-semibold">{r.axis}</td>
                  <td className="border-b border-line px-2.5 py-2.5 align-top">{r.offers}</td>
                  <td className="w-[16rem] border-b border-line px-2.5 py-2.5 align-top text-xs text-mute">{r.tier}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
