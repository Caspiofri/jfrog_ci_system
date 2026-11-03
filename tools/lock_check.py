"""Lock check (D59 step 3): every fingerprint must equal its value at the locked commit ae8fbb5; exit 1 on any difference.

Usage: .venv/bin/python tools/lock_check.py [CHECKOUT]   (default: the checkout this file is in; run it from the Pi's
main checkout, because the legacy classify_rank value hashes absolute paths and is 99b79890ceea only there)
"""
import sys
from pathlib import Path

LOCK = {"commit": "ae8fbb5ca786f4d5e1ac070a5fb66a57c133b2c7", "classify_rank": "99b79890ceea",
        "portable": "e04716a2a1d6", "lens": "1692c04ba7df", "insights": "e99d23e4edcf", "sheet_sha": "e7f13e0b3456"}


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from ci import eval_golden, insights, lens, run_meta

    now = {"classify_rank": eval_golden.fingerprint(), "portable": run_meta.portable_classify_rank(),
           "lens": lens.fingerprint(), "insights": insights.fingerprint(), "sheet_sha": run_meta.sheet_sha()}
    bad = {k: {"locked": LOCK[k], "now": v} for k, v in now.items() if v != LOCK[k]}
    print(f"checkout {root}, locked at {LOCK['commit'][:7]}: {now}")
    print("LOCK OK" if not bad else f"LOCK BROKEN: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
