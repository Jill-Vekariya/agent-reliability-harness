FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python \
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
