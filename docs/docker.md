# Docker

One image, three services: `ci` runs the collectors (`python -m ci.run`), `eval` scores the rules against the
golden set (`python -m ci.eval_golden`), and `labeling` serves the labeling page (`python -m ci.labeling`, port
8000, on 127.0.0.1 and optionally the Tailscale address; see below). None needs an API key (`eval --live` does). Images are built locally and pushed nowhere.

## Setup (once)

```sh
cp .env.example .env                              # optional; every value in it is optional
mkdir -p output data && touch evals/golden_set.jsonl
export APP_UID=$(id -u)                           # the container user gets your uid, so it can write those
```

Everything the app writes lives on the host, through bind mounts of the checkout's directories:

| host       | container      | what                                                                     |
|------------|----------------|--------------------------------------------------------------------------|
| `./data`   | `/app/data`    | dedupe history, the eval embedding cache (`data/ci/`)                    |
| `./output` | `/app/output`  | runs (`output/runs/`), eval reports and `test_runs.log` (`output/evals/`) |
| `./evals`  | `/app/evals`   | `golden_set.jsonl` (labels), `split_assignments.json`                    |

So runs and reports are plain files you can open, and nothing is lost with `--rm` or `docker compose down`.
`./evals` is mounted as a whole directory: a single-file mount would keep the old inode when the host file is
replaced (an editor's save, a `git checkout`), and the container would go on using a stale copy. Mounting it also
means the container runs the checkout's `evals/*.py`, which match the image as long as you rebuild after pulling.

`output`, `data` and `evals` must exist before any `docker compose` command that starts a container; a missing one
fails the start with `bind source path does not exist` (compose is told not to create it, because Docker would
create it root-owned and the app could not write to it). A missing `evals/golden_set.jsonl` is not an error for the
labeling page, which creates it on the first label, but the eval needs labels to score.

Set `APP_UID` to your uid: the image user gets that uid, so it can write to those directories, which you own.
Compose does not refuse a command without it: it falls back to 1000, which is enough for the demo (it writes only
inside the container) but not for the pipeline services if your uid is not 1000. Set it in the shell as above, or put
`APP_UID=1001` (your `id -u`) in `.env`, which compose also reads for `${...}` values. It is a build setting, so
after changing it run `docker compose build` again.

## Build and run (native: arm64 on the Pi, amd64 on a laptop)

```sh
docker compose build
docker compose run --rm ci                         # one run: output/runs/<run_id>.jsonl + report
docker compose run --rm ci --sources hackernews --days 2
docker compose run --rm eval --split train         # rules-only eval: output/evals/<timestamp>.json
docker compose run --rm eval --split test         # held-out split; also appends to output/evals/test_runs.log
docker compose up -d labeling                      # http://127.0.0.1:8000/
docker compose ps                                  # labeling turns "healthy" once /api/meta answers
docker compose logs -f labeling
docker compose down                                # stops; ./data, ./output and ./evals are untouched
```

`eval` sits behind the `eval` compose profile, so `docker compose up` does not start it; naming it in
`docker compose run` is enough. `docker compose run --rm ci` is the same image, so
`docker compose run --rm --entrypoint python ci -m ci.eval_golden --split train` works too.

To point a container at other host directories (a scratch copy for testing, so it never touches the real labels),
set `DATA_HOST_DIR`, `OUTPUT_HOST_DIR` or `EVALS_HOST_DIR`; each defaults to the checkout's directory. A scratch
`evals` must be a copy of the whole directory, since `ci.eval_golden` imports `evals.rank_split`.

## Who can reach the labeling page

Docker publishes ports with its own iptables rules, which run before ufw's: a port published on all interfaces
(`"8000:8000"`) is reachable from the whole LAN even when ufw denies it. So compose never publishes on all
interfaces. Inside the container the app binds `0.0.0.0` (`--host 0.0.0.0`, which it warns about; expected there,
since the published port arrives on the container's interface), and the host side is limited to:

- `127.0.0.1` always (`docker-compose.yml`);
- the Tailscale address, only with the override file `docker-compose.tailscale.yml`. It is a separate file rather
  than part of `docker-compose.yml` so that compose still works on a machine without Tailscale (a reviewer's
  laptop); with the override, a missing `TAILSCALE_IP` is an error, never a fallback to all interfaces.

On the Pi:

```sh
export TAILSCALE_IP=$(tailscale ip -4)
docker compose -f docker-compose.yml -f docker-compose.tailscale.yml up -d labeling
# http://127.0.0.1:8000/ on the Pi, http://$TAILSCALE_IP:8000/ from the tailnet; not the LAN address
```

To avoid repeating `-f`, put `COMPOSE_FILE=docker-compose.yml:docker-compose.tailscale.yml` and
`TAILSCALE_IP=100.x.y.z` in `.env`. `TAILSCALE_IP` must be the address at start time; if it changes, recreate the
container (`up -d --force-recreate labeling`), or Docker cannot bind it.

## Tests in the container

```sh
docker build --target test -t jfrog-ci:test --build-arg APP_UID=$(id -u) .
docker run --rm jfrog-ci:test                      # pytest -q, no API keys in the container
docker run --rm --entrypoint ruff jfrog-ci:test check --no-cache   # /app is read-only to the app user
```

## The other architecture

```sh
docker buildx build --platform linux/amd64 --target runtime -t jfrog-ci:amd64 --load .   # on the Pi
docker buildx build --platform linux/arm64 --target runtime -t jfrog-ci:arm64 --load .   # on an amd64 laptop
```

Building for a foreign architecture runs that architecture's binaries under QEMU, which must be registered once
per machine (it needs root):

```sh
sudo apt-get install -y qemu-user-static binfmt-support    # Debian / Raspberry Pi OS
# or: docker run --privileged --rm tonistiigi/binfmt --install amd64
```

`ls /proc/sys/fs/binfmt_misc/` then lists `qemu-x86_64` (or `qemu-aarch64`). Every dependency ships a wheel for
both architectures, so the foreign build compiles nothing; it is just slower under emulation.
