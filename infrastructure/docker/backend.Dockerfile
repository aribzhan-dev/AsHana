FROM ghcr.io/astral-sh/uv:0.13.3 AS uv
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
COPY backend/alembic.ini backend/logging.json ./
COPY backend/migrations ./migrations
RUN uv sync --frozen --no-dev --no-editable \
    && useradd --create-home --uid 10001 ashana
USER ashana
EXPOSE 8000
CMD ["uvicorn", "ashana.bootstrap.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers", "--log-config", "logging.json"]

FROM runtime AS test
USER root
RUN uv sync --frozen --no-editable
COPY backend/tests ./tests
USER ashana
CMD ["pytest", "-q", "-p", "no:cacheprovider"]
