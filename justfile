# https://just.systems

alias m := migrate
alias cr := create_revision
alias ct := create_types

# backend

migrate:
    uv run alembic upgrade heads

create_revision *MESSAGE:
    uv run alembic revision --autogenerate -m "{{ MESSAGE }}"

fast-dev: migrate
    uv run fastapi dev --port 42456

fast-prod: migrate
    uv run -m app.main

# update all uv packages
upgrade:
    uvx uv-upgrade

types:
    uv run basedpyright
    uv run djlint templates
    uv run ruff format --check app
    uv run alembic check

# frontend

astro-build:
    sh -c "(cd frontend && npm run build)"

astro-dev:
    sh -c "(cd frontend && npm run dev)"

astro-prod: astro-build
    sh -c "(cd frontend && npm run preview)"

watch:
    mise watch build -w frontend

create_types:
    # requires python server to be running with docs enabled
    npx @hey-api/openapi-ts -i http://localhost:42456/openapi.json -o frontend/src/client
