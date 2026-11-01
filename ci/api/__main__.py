"""python -m ci.api [--port 8010]: the CI API on 127.0.0.1 (no auth in the demo).

Logs go to the terminal and are appended to output/logs/ci_api.log (D48), so they survive a reboot. No rotation yet.
"""
import argparse
import copy
from pathlib import Path

import uvicorn
import uvicorn.config

from ci.api.app import create_app
from config.settings import OUTPUT_DIR

HOST = "127.0.0.1"  # loopback only, never a CLI option: the API has no login (contract 2.1)
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


def build_app():
    """The live app: Refresh insights (D37) gets the Gemini model and the embedding function the daily run uses."""
    from ci.dedupe import default_embedding_fn
    from ci.llm import GeminiLLM

    return create_app(insights_llm=GeminiLLM, embed_fn=default_embedding_fn())


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m ci.api", description=__doc__)
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args(argv)
    uvicorn.run(build_app(), host=HOST, port=args.port, log_config=log_config())


if __name__ == "__main__":
    main()
