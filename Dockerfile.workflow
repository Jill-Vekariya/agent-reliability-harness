ARG BASE_IMAGE=python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
FROM ${BASE_IMAGE}
ARG SOURCE_REVISION=uncommitted
ARG SOURCE_DIGEST=unrecorded
LABEL org.opencontainers.image.revision=${SOURCE_REVISION} \
    io.arh.workflow.source_digest=${SOURCE_DIGEST} \
    org.opencontainers.image.title="Harness local durable fixture jobs"
USER root
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" \
    ARH_PROJECT_ROOT=/app API_BUDGET_USD=0 ARH_WORKFLOW_MODE=local ARH_WORKFLOW_CONTAINER=1 \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
RUN /usr/local/bin/python -m pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock .python-version ./
COPY src ./src
RUN uv sync --locked --extra workflow --no-editable --no-cache --reinstall-package agent-reliability-harness
COPY . .
RUN (getent group app || groupadd --gid 10001 app) \
    && (id app || useradd --uid 10001 --gid app --no-create-home app) \
    && mkdir -p /reports && chown app:app /reports
USER 10001:10001
HEALTHCHECK NONE
CMD ["arh", "jobs", "serve", "--host", "0.0.0.0", "--port", "8091"]
