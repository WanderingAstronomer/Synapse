# ============================================================================
# Synapse — Multi-Stage Dockerfile
# ============================================================================
# This Dockerfile builds a lean production image for the Synapse bot.
#
# Strategy:
#   Stage 1 ("builder") — Install uv, resolve & install all Python
#     dependencies into a .venv.  This layer is cached aggressively.
#   Stage 2 ("runtime") — Copy ONLY the .venv and source code into a
#     minimal Python image.  No build tools, no uv, no cache.
#
# The result is a small, reproducible image that starts fast and has a
# minimal attack surface.
# ============================================================================

# ── Stage 1: Builder ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Grab the uv binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Compile bytecode at install time for faster cold starts.
ENV UV_COMPILE_BYTECODE=1
# Use copy mode — required when cache and target are on different filesystems.
ENV UV_LINK_MODE=copy

# Install dependencies FIRST (this layer changes rarely → cached).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy the full project source and install it.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# ── Stage 2: Runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim

# Copy the pre-built virtual environment from the builder.
COPY --from=builder /app/.venv /app/.venv

# uv may create the venv using an uv-managed Python interpreter (a symlink under
# /root/.local/share/uv/python). Copy that interpreter into the runtime image so
# the venv entrypoints remain valid.
COPY --from=builder /root/.local/share/uv/python /root/.local/share/uv/python

# Put the venv at the front of PATH so `python` resolves to the right one.
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code + config.
COPY . /app
WORKDIR /app

# Default command — overridden in docker-compose.yml per service.
CMD ["python", "-m", "synapse.bot"]
