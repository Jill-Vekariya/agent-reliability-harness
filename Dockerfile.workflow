ARG BASE_IMAGE=python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
FROM ${BASE_IMAGE} AS runtime
USER root
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python PATH="/app/.venv/bin:$PATH" \
    ARH_PROJECT_ROOT=/app API_BUDGET_USD=0 ARH_WORKFLOW_MODE=local ARH_WORKFLOW_CONTAINER=1 \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
RUN /usr/local/bin/python -m pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --extra workflow --no-install-project --no-editable
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --extra workflow --no-editable --reinstall-package agent-reliability-harness
COPY . .
RUN (getent group app || groupadd --gid 10001 app) \
    && (id app || useradd --uid 10001 --gid app --no-create-home app) \
    && mkdir -p /reports && chown app:app /reports
ENV ARH_ARTIFACT_DIR=/reports/artifacts
USER 10001:10001
HEALTHCHECK NONE
CMD ["arh", "jobs", "serve", "--host", "0.0.0.0", "--port", "8091"]
ARG SOURCE_REVISION=uncommitted
ARG SOURCE_DIGEST=unrecorded
LABEL org.opencontainers.image.revision=${SOURCE_REVISION} \
    io.arh.workflow.source_digest=${SOURCE_DIGEST} \
    org.opencontainers.image.title="Harness local durable fixture jobs"

# Git is required by provenance tests, not by the application runtime.
FROM runtime AS checks
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001

