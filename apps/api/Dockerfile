# syntax=docker/dockerfile:1

# ---- build ----------------------------------------------------------------
FROM python:3.12-slim AS build

# uv resolves and installs from the lockfile far faster than pip, and pins
# exactly what CI tested.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first: source changes must not invalidate the install.
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && VIRTUAL_ENV=/opt/venv uv pip install -r pyproject.toml

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    VIRTUAL_ENV=/opt/venv uv pip install --no-deps -e .

# ---- runtime --------------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 10001 bsa && \
    mkdir -p /data/objectstore && \
    chown bsa:bsa /data/objectstore

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app

# Never run as root. Cloud Run does not require it and a container escape is
# meaningfully worse from a root process.
USER bsa

EXPOSE 8000

# Cloud Run supplies $PORT; default to 8000 for compose.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn bsa.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
