# https://just.systems

alias d := dev
alias m := migrate
alias cr := create_revision

# backend

migrate:
    uv run alembic upgrade heads

create_revision *MESSAGE:
    uv run alembic revision --autogenerate -m "{{ MESSAGE }}"

dev: migrate
    uv run fastapi dev

# update all uv packages
upgrade:
    uvx uv-upgrade

types:
    uv run basedpyright
    uv run djlint templates
    uv run ruff format --check app
    uv run alembic check

# frontend

build:
    sh -c "(cd frontend && npm run build)"

watch:
    mise watch build -w frontend

create_types:
    # requires python server to be running with docs enabled
    npx @hey-api/openapi-ts -i http://localhost:8000/openapi.json -o frontend/src/client
