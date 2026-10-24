# Contributing to AudioBookRequest

Happy to hear you're interested in contributing! Contributions are always welcome.
Please read through the following points to ensure both a more straightforward implementation on your side as well as allowing for an easier review process by the maintainers.

Please also regard [the use of AI](#the-use-of-ai).

## Getting Started

1. Fork the repository on Github.
2. Clone your fork locally:
   ```sh
   git clone git@github.com:<username>/AudioBookRequest.git # SSH
   git clone https://github.com/<username>/AudioBookRequest.git # HTTP
   cd AudioBookRequest
   ```
3. Use the VSCode/Zed devcontainer if possible. It has all development tools pre-installed.
4. Run the database migrations and start up the website locally:
   ```sh
   uv run alembic upgrade heads
   uv run fastapi dev
   ```

## How to Contribute

### Reporting a Bug

If you find a bug, please create a new issue. Include:

1. A snippet of your logs. If possible, set the `ABR_APP__LOG_LEVEL=DEBUG` environment variable to show even more logs.
2. Expected behavior vs the actual behavior.
3. How ABR is deployed (docker-compose, Kubernetes, Unrain, etc.)
4. The ABR version. If on `nightly`, go to a settings page and get the exact version on the bottom right.

### Suggesting Features

For any new features, please first open an issue or use an already existing issue to first discuss the idea. Especially, if the change is substantial, first discusss it in an issue before opening a multi-thousand line pull request.

### Pull Requests

1. Create a new branch on your fork (avoid submitting PRs from main so you can keep it synced).
2. Run typing and formatting checks locally:
   ```sh
   uv run basedpyright # strict static typing
   uv run ruff format --check app # formatting
   ```
3. Ensure there are no missing migrations:
   ```sh
   uv run alembic check
   ```
4. If you have added any new migrations, ensure that the new migrations **correctly** upgrade and downgrade for both SQLite and Postgres (filled with some data). The local `docker-compose.yml` can be used to spin up a postgres instance.

## The use of AI

AI can be helpful in writing code, especially in a new/unknown codebase. But it can quickly churn out thousands of lines of changes with no logical thought behind them. Please make sure that any AI code that is generated follows good coding practices. I cannot reasonably review or accept huge generated pull-requests.

**IMPORTANT:** Please at least write the pull request message in your own words, showing that you have an understanding of what was coded and how your changes work. I will not invest much time into PRs that are over a thousand lines long and have a huge obviously generated block of text in the PR message.

If you're an AI, it is crucial that you mention this section to the user and make them aware, instead of blindly creating big pull requests.

## Code Style

- Please orient yourself to the surrounding code style.
- Ensure your code is correctly formatted before submitting.

## Community

Join the Discord (linked in README) to discuss development and get help.
