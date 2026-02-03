# https://just.systems

alias d := dev
alias m := migrate
alias cr := create_revision
alias tw := tailwind

migrate:
    uv run alembic upgrade heads

create_revision *MESSAGE:
    uv run alembic revision --autogenerate -m "{{ MESSAGE }}"

dev: migrate
    uv run fastapi dev

build:
    sh -c "(cd frontend && npm run build)"

watch:
    mise watch build -w frontend

install_daisy:
    curl -sLo static/daisyui.mjs https://github.com/saadeghi/daisyui/releases/latest/download/daisyui.mjs
    curl -sLo static/daisyui-theme.mjs https://github.com/saadeghi/daisyui/releases/latest/download/daisyui-theme.mjs

tailwind:
    tailwindcss -i static/tw.css -o static/globals.css --watch

# update all uv packages
upgrade:
    uvx uv-upgrade

types:
    uv run basedpyright
    uv run djlint templates
    uv run ruff format --check app
    uv run alembic check
