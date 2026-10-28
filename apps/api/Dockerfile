ARG DOCKER_REGISTRY_PREFIX=
FROM ${DOCKER_REGISTRY_PREFIX}python:3.11-slim

ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY scripts ./scripts
COPY data ./data
COPY training ./training
COPY experiments ./experiments
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" ".[observability]" \
    && addgroup --system text2sql \
    && adduser --system --ingroup text2sql text2sql \
    && mkdir -p /app/data/state /app/data/interim /app/experiments/reports \
    && chown -R text2sql:text2sql /app/data/state /app/data/interim /app/experiments/reports
USER text2sql
CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

