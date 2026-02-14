# ---- CSS ----
FROM alpine:3.23 AS css
WORKDIR /app

RUN apk add --no-cache curl build-base && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        TAILWIND_ARCH="x64"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        TAILWIND_ARCH="arm64"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    curl -L "https://github.com/tailwindlabs/tailwindcss/releases/download/v4.1.18/tailwindcss-linux-${TAILWIND_ARCH}-musl" \
         -o /bin/tailwindcss && \
    chmod +x /bin/tailwindcss

RUN mkdir -p static && \
    curl -Lo static/daisyui.mjs https://github.com/saadeghi/daisyui/releases/latest/download/daisyui.mjs && \
    curl -Lo static/daisyui-theme.mjs https://github.com/saadeghi/daisyui/releases/latest/download/daisyui-theme.mjs

COPY templates/ templates/
COPY static/tw.css static/tw.css
RUN /bin/tailwindcss -i static/tw.css -o static/globals.css -m

# ---- Python deps ----
FROM astral/uv:python3.14-alpine AS python-deps
WORKDIR /app
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-cache --no-dev
COPY app/util/fetch_js.py app/util/fetch_js.py
RUN mkdir -p static && /app/.venv/bin/python app/util/fetch_js.py

# ---- Final ----
FROM python:3.14-alpine AS final
WORKDIR /app

COPY --from=css /app/static/globals.css static/globals.css
COPY --from=python-deps /app/.venv /app/.venv
COPY --from=python-deps /app/static static/

COPY static/ static/
COPY alembic/ alembic/
COPY alembic.ini alembic.ini
COPY templates/ templates/
COPY app/ app/
COPY CHANGELOG.md CHANGELOG.md

ENV ABR_APP__PORT=8000
ARG VERSION
ENV ABR_APP__VERSION=$VERSION

CMD /app/.venv/bin/alembic upgrade heads && /app/.venv/bin/fastapi run --port $ABR_APP__PORT --proxy-headers --forwarded-allow-ips="${ABR_APP__FORWARDED_ALLOW_IPS:-0.0.0.0/0}"
