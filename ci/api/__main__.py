"""python -m ci.api [--port 8010]: the CI API on 127.0.0.1 (no auth in the demo)."""
import argparse

import uvicorn

from ci.api.app import create_app


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m ci.api", description=__doc__)
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args(argv)
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
