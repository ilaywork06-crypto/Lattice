# Build context is the repository root (see docker-compose.yml)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# Workspace metadata + all member sources (uv resolves the whole workspace)
COPY pyproject.toml uv.lock* ./
COPY packages ./packages
COPY services ./services

RUN uv sync --frozen --no-dev --package lattice-core

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-dev", "--package", "lattice-core", \
     "uvicorn", "lattice_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
