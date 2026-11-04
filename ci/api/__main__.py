"""python -m ci.api [--port 8010]: the CI API on 127.0.0.1 (no auth in the demo).

Logs go to the terminal and are appended to output/logs/ci_api.log (D48), so they survive a reboot. No rotation yet.
"""
import argparse
import copy
import os
from pathlib import Path

import uvicorn
import uvicorn.config

from ci.api.app import create_app
from config.settings import OUTPUT_DIR

HOST = "127.0.0.1"  # loopback by default and never a CLI option: the API has no login (contract 2.1)
LOG_PATH = OUTPUT_DIR / "logs" / "ci_api.log"
FILE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def log_config(path: Path = LOG_PATH) -> dict:
    """uvicorn's own logging, plus one file handler for its loggers and the app's (the root logger)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    cfg["formatters"]["file"] = {"format": FILE_FORMAT}
    cfg["handlers"]["file"] = {"class": "logging.FileHandler", "filename": str(path), "encoding": "utf-8",
                               "formatter": "file"}
    for name in ("uvicorn", "uvicorn.access"):
        cfg["loggers"][name]["handlers"] = [*cfg["loggers"][name]["handlers"], "file"]
    cfg["loggers"][""] = {"handlers": ["default", "file"], "level": "INFO"}
    return cfg


def build_app(demo_dir: Path | None = None):
    """The live app: Refresh insights (D37) gets the Gemini model and the embedding function the daily run uses.
    With demo_dir, the demo app on that snapshot: no model, no embedding model, no key needed (ci.demo). Writable on
    a fresh temporary copy by default (D111); read-only with CI_DEMO_READ_ONLY=1 or when the startup guard fails."""
    if demo_dir is not None:
        from ci import demo

        m = demo.prepare(demo_dir)
        if m["writable"]:  # printed: uvicorn's logging is set up only after this
            g = m["guard"]
            print(f"demo: WRITABLE on a temporary copy ({m['copy_dir']}); startup guard: 0 rows changed in "
                  f"{g['tables']} tables ({g['rows']} rows); every action resets on restart", flush=True)
        else:
            print(f"demo: READ-ONLY ({m['read_only_reason']}); writes answer 403 demo_read_only", flush=True)
        return create_app(demo=m)
    from ci.dedupe import default_embedding_fn
    from ci.llm import GeminiLLM

    return create_app(insights_llm=GeminiLLM, embed_fn=default_embedding_fn())


def listen_host(env: dict[str, str] | None = None) -> str:
    """127.0.0.1, unless CI_API_HOST says otherwise. Only the container sets it (0.0.0.0 inside, with the published
    port bound to the host's loopback in docker-compose.yml)."""
    if env is None:
        return os.environ.get("CI_API_HOST", "") or HOST
    return env.get("CI_API_HOST", "") or HOST


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m ci.api", description=__doc__)
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--demo", type=Path, metavar="SNAPSHOT_DIR", default=os.environ.get("CI_DEMO_DIR") or None,
                    help="serve this demo snapshot (python -m ci.demo build) instead of the live store: writable on a "
                         "temporary copy, or read-only with CI_DEMO_READ_ONLY=1")
    args = ap.parse_args(argv)
    host = listen_host()
    if host != HOST:
        print(f"WARNING: listening on {host}; only do this inside a container whose published port is restricted")
    uvicorn.run(build_app(args.demo), host=host, port=args.port, log_config=log_config())


if __name__ == "__main__":
    main()
