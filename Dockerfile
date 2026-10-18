FROM python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" ARH_PROJECT_ROOT=/app \
    ARH_ARTIFACT_DIR=/reports/artifacts MPLCONFIGDIR=/tmp/matplotlib \
    API_BUDGET_USD=0
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock .python-version ./
COPY src ./src
RUN uv sync --locked --no-editable --no-cache
COPY . .
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /reports && chown app:app /reports
USER 10001:10001
EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=3)"
CMD ["streamlit", "run", "src/agent_reliability/viewer/app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.fileWatcherType", "none"]
