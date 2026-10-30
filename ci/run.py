"""CI run entrypoint: python -m ci.run [--sources google_news,hackernews] [--fresh] [--days N]. Needs no API keys."""
import argparse
import sys

from ci import config
from ci.pipeline import COLLECTORS, format_report, run


def main(argv: list[str] | None = None) -> None:
    """Exits 1 when every source failed (report.json status "failed", no <run_id>.jsonl)."""
    ap = argparse.ArgumentParser(prog="python -m ci.run", description=__doc__)
    ap.add_argument("--sources", help=f"comma-separated subset of: {','.join(COLLECTORS)}")
    ap.add_argument("--fresh", action="store_true", help="ignore earlier runs when deduping (for re-testing)")
    ap.add_argument("--days", type=int, help="collection window in days (overrides window_days in config)")
    args = ap.parse_args(argv)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None
    unknown = set(sources or []) - set(COLLECTORS)
    if unknown:
        ap.error(f"unknown source(s): {', '.join(sorted(unknown))}")

    result = run(config.load(), sources=sources, fresh=args.fresh, days=args.days)
    print(format_report(result.report))
    for path in result.paths.values():
        print(f"wrote {path}")
    if result.failed:
        print(f"FAILED: {result.report['status_reason']} (no {result.run_id}.jsonl written)")
        sys.exit(1)


if __name__ == "__main__":
    main()
