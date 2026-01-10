# https://just.systems

alias d := dev
alias m := migrate
alias cr := create_revision
alias tw := tailwind

migrate:
    uv run alembic upgrade heads

create_revision *MESSAGE:
    uv run alembic revision --autogenerate -m "{{MESSAGE}}"

dev: migrate
    uv run fastapi dev

node_modules:
    npm install

tailwind: node_modules
    tailwindcss -i static/tw.css -o static/globals.css --watch

types:
    uv run basedpyright
    uv run djlint templates
    uv run ruff format --check app
    uv run alembic check
