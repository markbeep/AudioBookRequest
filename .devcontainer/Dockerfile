FROM node:23-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y sqlite3 vim

RUN npm install -g rust-just

RUN curl -L -o /bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.1.18/tailwindcss-linux-x64 && \
    chmod +x /bin/tailwindcss

