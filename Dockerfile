# Stage 1: Node.js dependencies (for DaisyUI/TailwindCSS)
FROM node:23-alpine3.20 AS node-deps

WORKDIR /app

# Copy package files and install dependencies (cached layer)
COPY package.json package-lock.json ./
RUN npm ci --only=production --no-audit --no-fund

# Stage 2: TailwindCSS binary download (platform-specific)
FROM python:3.12-alpine AS tailwind-binary

WORKDIR /app

# Install dependencies and download TailwindCSS in a single layer
RUN apk add --no-cache curl gcompat build-base && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        TAILWIND_ARCH="x64"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        TAILWIND_ARCH="arm64"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    curl -L "https://github.com/tailwindlabs/tailwindcss/releases/download/v4.0.6/tailwindcss-linux-${TAILWIND_ARCH}-musl" \
         -o /bin/tailwindcss && \
    chmod +x /bin/tailwindcss

# Stage 3: Python dependencies
FROM python:3.12-alpine AS python-deps

WORKDIR /app

# Install system dependencies needed for Python packages
RUN apk add --no-cache gcompat build-base

# Copy uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files and install Python dependencies (cached layer)
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-cache --no-dev

# Stage 4: Final application image
FROM python:3.12-alpine AS final

WORKDIR /app

# Install runtime dependencies (including C++ libraries for TailwindCSS binary)
RUN apk add --no-cache gcompat libstdc++ libgcc

# Copy binaries and dependencies from previous stages
COPY --from=tailwind-binary /bin/tailwindcss /bin/tailwindcss
COPY --from=node-deps /app/node_modules/ ./node_modules/
COPY --from=python-deps /app/.venv/ ./.venv/
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy configuration files (less frequently changed)
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Copy static assets and templates (moderately frequently changed)
COPY static/ ./static/
COPY templates/ ./templates/
COPY CHANGELOG.md ./

# Copy application code (most frequently changed - last for better caching)
COPY app/ ./app/

# Build CSS and fetch JS files in a single layer
RUN /bin/tailwindcss -i static/tw.css -o static/globals.css -m && \
    .venv/bin/python /app/app/util/fetch_js.py

ENV ABR_APP__PORT=8000
ARG VERSION
ENV ABR_APP__VERSION=$VERSION

CMD /app/.venv/bin/alembic upgrade heads && /app/.venv/bin/fastapi run --port $ABR_APP__PORT

