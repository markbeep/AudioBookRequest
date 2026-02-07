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

install_daisy:
    curl -sLo static/daisyui.mjs https://github.com/saadeghi/daisyui/releases/latest/download/daisyui.mjs
    curl -sLo static/daisyui-theme.mjs https://github.com/saadeghi/daisyui/releases/latest/download/daisyui-theme.mjs

tailwind:
    tailwindcss -i static/tw.css -o static/globals.css --watch

# update all uv packages
upgrade:
    uvx uv-upgrade

format_html:
    uv run djlint templates --extension=jinja --reformat

types:
    uv run basedpyright
    uv run djlint templates --extension=jinja --check
    uv run ruff format --check app
    uv run alembic check
