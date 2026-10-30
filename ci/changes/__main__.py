"""Change detection: python -m ci.changes [--competitors jfrog,snyk] [--live]

Without --live: a dry run that fetches and hashes the tracked pages against the stored snapshots (no LLM, no key,
nothing written). With --live: extracts with Gemini on new or changed pages, updates the snapshots and head-to-head
cells under data/ci/, and writes output/changes/<run_id>.jsonl (the Changes items) and <run_id>.report.json.
"""
import argparse
import logging
import sys

from ci import config as ci_config
from ci.changes import config
from ci.changes.run import format_report, run


def main(argv: list[str] | None = None) -> None:
    """Exits 1 when every page failed."""
    ap = argparse.ArgumentParser(prog="python -m ci.changes", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competitors", help="comma-separated competitor keys from config/tracked_pages.yaml")
    ap.add_argument("--live", action="store_true", help="extract with the real Gemini and store the results")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    pages = config.load()
    chosen = [c.strip() for c in args.competitors.split(",") if c.strip()] if args.competitors else None
    unknown = set(chosen or []) - set(pages.competitors)
    if unknown:
        ap.error(f"unknown competitor(s): {', '.join(sorted(unknown))}")
    names = {c.key: c.name for c in ci_config.load().competitors}
    llm = None
    if args.live:
        from ci.llm import GeminiLLM
        llm = GeminiLLM()
    result = run(pages, llm=llm, names=names, competitors=chosen)
    print(format_report(result.report))
    for path in result.paths.values():
        print(f"wrote {path}")
    if result.report["status"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
