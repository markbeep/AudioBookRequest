FROM node:23-bookworm

# dev tools
RUN apt-get update && apt-get install -y \
    sqlite3\
    vim \
    less
RUN npm install -g rust-just
# jj
RUN curl -Lo jj.tar.gz https://github.com/jj-vcs/jj/releases/download/v0.37.0/jj-v0.37.0-x86_64-unknown-linux-musl.tar.gz && \
tar -xzf jj.tar.gz -C /bin ./jj && \
rm jj.tar.gz && \
chmod +x /bin/jj
ENV EDITOR=vim

# project tools
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN curl -L -o /bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.1.18/tailwindcss-linux-x64 && \
    chmod +x /bin/tailwindcss

