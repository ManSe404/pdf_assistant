# One image: the built web client served by the API.
#   docker compose up --build    ->  http://localhost:8000
# Data (SQLite, uploaded PDFs, embedded Qdrant) lives in the /data volume.

FROM node:24-alpine AS client
WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client ./
RUN npm run build


FROM python:3.14-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data \
    CLIENT_DIR=/app/client
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir /data && chown app:app /data
WORKDIR /app
COPY --from=backend --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app backend/alembic.ini ./
COPY --chown=app:app backend/alembic ./alembic
COPY --from=client --chown=app:app /client/build /app/client
USER app
VOLUME /data
EXPOSE 8000
# One container with a SQLite file: bring the schema up to date, then serve.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn pdf_assistant.api.main:create_app --factory --host 0.0.0.0 --port 8000"]
