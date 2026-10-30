"""Serve the labeling page on localhost and Tailscale: python -m ci.labeling [--run <run_id>] [--port 8000]."""
import argparse
import logging
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from ci.labeling import hosts as hosts_mod
from ci.labeling.app import LABELS_PATH, RUNS_DIR, create_app


def main() -> None:
    ap = argparse.ArgumentParser(description="JFrog CI labeling page")
    ap.add_argument("--run", help="run id to open first (default: newest in the runs dir)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", action="append", dest="hosts", metavar="HOST",
                    help="address to listen on; repeatable (default: 127.0.0.1 + the Tailscale IP, or $LABELING_HOSTS)")
    ap.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    ap.add_argument("--labels", type=Path, default=LABELS_PATH)
    ap.add_argument("--rebuild-queue", action="store_true",
                    help="rebuild the labeling queue of --run (default: newest) from the current rules, then serve")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = create_app(runs_dir=args.runs_dir, labels_path=args.labels, default_run=args.run)
    if args.rebuild_queue:
        with TestClient(app) as client:  # same code path as the API, without a running server
            run = client.get("/api/meta").json()["default_run"]
            r = client.post(f"/api/runs/{run}/queue/rebuild")
            r.raise_for_status()
            sizes = ", ".join(f"{b['name']} {b['target']}" for b in r.json()["buckets"])
            print(f"Rebuilt the queue for {run}: {sizes}")
    hosts = hosts_mod.resolve_hosts(args.hosts)
    if warning := hosts_mod.wildcard_warning(hosts):
        print(warning)
    sockets = hosts_mod.bind(hosts, args.port)
    urls = ", ".join(f"http://{f'[{h}]' if ':' in h else h}:{args.port}/" for h in hosts)
    print(f"Labeling {args.runs_dir} -> {args.labels} on {urls}")
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=sockets)


if __name__ == "__main__":
    main()
