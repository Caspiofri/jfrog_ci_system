# syntax=docker/dockerfile:1
# JFrog CI tool. Multi-arch: linux/arm64 (the Pi) and linux/amd64. Build and run: docs/docker.md.
#   docker build -t jfrog-ci .                      runtime image (default target)
#   docker build --target test -t jfrog-ci:test .   runtime + pytest/ruff; its default command runs the suite

# ---- deps: python + pinned runtime packages + the embedding model. Rebuilt only when requirements.txt changes.
FROM python:3.11-slim AS deps
ARG APP_UID=1000
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    HOME=/home/app
RUN useradd --create-home --uid "${APP_UID}" app
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
# chromadb's ONNX all-MiniLM-L6-v2 downloads on first use; fetch it now so runs and tests need no download
USER app
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as E; E()(['warm up'])"
USER root
# the only places the app writes; compose bind-mounts host dirs over them (owned by APP_UID on the host),
# so this ownership matters only for a plain `docker run` without mounts
RUN mkdir -p /app/data /app/output /app/evals && chown app:app /app/data /app/output /app/evals

# ---- test: the commit gate inside the container
FROM deps AS test
COPY requirements-dev.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-dev.txt
COPY . .
RUN chown app:app /app/evals
USER app
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

# ---- runtime (default): code is root-owned and read-only to the app user
FROM deps AS runtime
COPY . .
RUN chown app:app /app/evals
USER app
EXPOSE 8000
# a CI run by default (docker run jfrog-ci --sources hackernews); compose overrides it for the labeling page
ENTRYPOINT ["python", "-m", "ci.run"]
