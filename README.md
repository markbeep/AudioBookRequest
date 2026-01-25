![GitHub Release](https://img.shields.io/github/v/release/markbeep/AudioBookRequest?style=for-the-badge)
![Python Version](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fmarkbeep%2FAudioBookRequest%2Fmain%2Fpyproject.toml&style=for-the-badge&logo=python)
[![Discord](https://img.shields.io/discord/1350874252282171522?style=for-the-badge&logo=discord&link=https%3A%2F%2Fdiscord.gg%2FSsFRXWMg7s)](https://discord.gg/SsFRXWMg7s)

![Header](/media/AudioBookRequestIcon.png)

Your tool for handling audiobook requests on a Plex/Audiobookshelf/Jellyfin instance.

If you've heard of Overseer, Ombi, or Jellyseer; this is in the similar vein, <ins>but for audiobooks</ins>.

![Search Page](/media/search_page.png)

## Table of Contents

- [Motivation](#motivation)
  - [Features](#features)
- [Getting Started](#getting-started)
  - [Quick Start](#quick-start)
  - [Basic Usage](#basic-usage)
  - [Documentation](#documentation)
    - [Auto download](#auto-download)
    - [Audiobookshelf Integration](#audiobookshelf-integration)
    - [OpenID Connect](#openid-connect)
      - [Getting locked out](#getting-locked-out)
    - [Environment Variables](#environment-variables)
- [Contributing](#contributing)
  - [Conventional Commits](#conventional-commits)
  - [Local Development](#local-development)
  - [Initialize Database](#initialize-database)
  - [Running](#running)
  - [Docker Compose](#docker-compose)
- [Docs](#docs)
- [Tools](#tools)

# Motivation

AudioBookRequest aims to be a simple and lightweight tool for managing audiobook requests for your media server. It should be easy to set up and use, while integrating nicely with other common tools in the \*arr stack. AudioBookRequest serves as as the frontend for you and your friends to easily make audiobook wishlists or create requests in an organized fashion.

It is not intended as a full replacement for Readarr/Chaptarr, but instead intended to be used alongside them.

## Features

- Employs the Audible API to make it easy to search for and request audiobooks.
- Add manual audiobook requests for any books not available on Audible.
- Easy user management. Only three assignable groups, made to get out of your way.
- Automatic downloading of requests. Integrate Prowlarr to use all your existing indexer settings and download clients.
- Send notifications to your favorite notification service (apprise, gotify, discord, ntfy, etc.).
- Single image deployment. You can deploy and create your first requests in under 5 minutes.
- SQLite and Postgres support!
- Lightweight website. No bulky javascript files, allowing you to use the website even on low bandwidth.
- Mobile friendly. Search for books for accept requests on the go!

---

# Getting Started

AudioBookRequest is intended to be deployed using Docker or Kubernetes. For "bare-metal" deployments, head to the [local development](#Contributing) section.

## Quick Start

Run the image directly:

```bash
docker run -p 8000:8000 -v $(pwd)/config:/config markbeep/audiobookrequest:1
```

Then head to http://localhost:8000.

**NOTE:** AudioBookRequest uses the `/config` directory inside the container for storing configs and data. Mount that directory locally somewhere to ensure persistent data across restarts.

## Basic Usage

1. Logging in the first time the login-type and root admin user has to be configured.
2. Head to `Settings>Users` to create accounts for your friends.
3. Any user can search for books and request them by clicking the `+` button.
4. The admin can head to the wishlist to see all the books that have been requested.

## Documentation

Head to https://markbeep.github.io/AudioBookRequest/ for more detailed documentation and tutorials.

### Auto download

Auto-downloading enables requests by `Trusted` and `Admin` users to directly start downloading once requested.

1. Ensure your Prowlarr instance is correctly set up with any indexers and download clients you want. [More info](https://prowlarr.com/).
2. On Prowlarr, head to `Settings>General` and copy the `API Key`.
3. On AudioBookRequest, head to `Settings>Prowlarr` and enter the API key as well as the base URL of your Prowlarr instance, i.e. `https://prowlarr.example.com`.
4. Head to `Settings>Download` to configure the automatic download settings:
   1. Enable `Auto Download` at the top.
   2. The remaining heuristics determine the ranking of any sources retrieved from Prowlarr.
   3. Indexer flags allow you to add priorities to certain sources like freeleeches.

### Audiobookshelf Integration

Audiobookshelf (ABS) integration lets ABR:

- Check if a book already exists in your ABS library and mark it as downloaded in search results to avoid duplicate requests.
- Trigger a library scan in ABS when a request is marked as downloaded in ABR (manual or automatic), so the new item appears quickly.

Setup steps:

1. In ABS, create an API token for an account with access to your audiobook library (Admin recommended).
2. In ABR, go to Settings > Audiobookshelf and enter:

- Base URL of your ABS server (e.g. https://abs.example.com or http://localhost:13378)
- API Token from step 1
- Select the target Library
- Enable “Use ABS to mark existing books as downloaded” if you want ABR to flag existing titles during search.

Notes:

- ABR searches ABS by ASIN and by “title + first author” to detect existing books; this is a best-effort match and may not catch every case depending on your metadata.
- ABS is automatically asked to scan after successful downloads are marked in ABR. ABS typically auto-detects updates, but this helps pick up changes sooner.

### OpenID Connect

OIDC allows you to use an external authentication service (Authentik, Keycloak, etc.) for user and group authentication. It can be configured in `Settings>Security`. The following six settings are required to successfully set up oidc. Ensure you use the correct values. Incorrect values or changing values on your authentication server in the future can cause lead to locking you out of the service. In those cases head to [`Getting "locked" out`](#getting-locked-out).

- `well-known` configuration endpoint: This is located at `/realms/{realm-name}/.well-known/openid-configuration` for keycloak or `/application/o/{issuer}/.well-known/openid-configuration` for authentik.
- username claim: The claim that should be used for usernames. The username has to be unique. **NOTE:** Any user logging in with the username of the root admin account will be root admin, no matter what group they're assigned.
- group claim: This is the claim that contains the group of each user. It should either be a string or a list of strings with one of the following case-insensitive values: `untrusted`, `trusted`, or `admin`. Any user without any groups is assigned the `untrusted` role.
- scope: The scopes required to get all the necessary information. The scope `openid` is almost **always** required. You need to add all required scopes to that the username and group claim is available.
- client id
- client secret

In your auth server settings, make sure you allow for redirecting to `/auth/oidc`. The oidc-login flow will redirect you there after you log in. Additionally, the access token expiry time from the authentication server will be used if provided. This might be fairly low by default.

Applying settings does not directly invalidate your current session. To test OIDC-settings, press the "log out" button to invalidate your current session.

#### Getting locked out

In the case of an OIDC misconfiguration, i.e. changing a setting like your client secret on your auth server, can cause you to be locked out. In these cases, you can head to `/login?backup=1`, where you can log in using your root admin credentials allowing you to correctly configure any settings.

### Environment Variables

| ENV                           | Description                                                                                                                                                                                                                                                  | Default          |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| `ABR_APP__PORT`               | The port to run the server on.                                                                                                                                                                                                                               | 8000             |
| `ABR_APP__DEBUG`              | If to enable debug mode. Not recommended for production.                                                                                                                                                                                                     | false            |
| `ABR_APP__OPENAPI_ENABLED`    | If set to `true`, enables an OpenAPI specs page on `/docs`.                                                                                                                                                                                                  | false            |
| `ABR_APP__CONFIG_DIR`         | The directory path where persistant data and configuration is stored. If ran using Docker or Kubernetes, this is the location a volume should be mounted to.                                                                                                 | /config          |
| `ABR_APP__LOG_LEVEL`          | One of `DEBUG`, `INFO`, `WARN`, `ERROR`.                                                                                                                                                                                                                     | INFO             |
| `ABR_APP__BASE_URL`           | Defines the base url the website is hosted at. If the website is accessed at `example.org/abr/`, set the base URL to `/abr/`                                                                                                                                 |                  |
| `ABR_DB__SQLITE_PATH`         | If relative, path and name of the sqlite database in relation to `ABR_APP__CONFIG_DIR`. If absolute (path starts with `/`), the config dir is ignored and only the absolute path is used.                                                                    | db.sqlite        |
| `ABR_APP__DEFAULT_REGION`     | Default audible region to use for the search. Has to be one of `us, ca, uk, au, fr, de, jp, it, in, es, br`.                                                                                                                                                 | us               |
| `ABR_APP__FORCE_LOGIN_TYPE`   | Forces the login type and prevents it from being modified. Can be one of `basic`, `forms`, `oidc`, or `none` to disable the login. `oidc` requires both the `ABR_APP__INIT_ROOT_USERNAME` and `ABR_APP__INIT_ROOT_PASSWORD` environment variables to be set. |                  |
| `ABR_APP__INIT_ROOT_USERNAME` | Sets the initial username of the root user when first launching ABR. Has no effect if a root admin already exists.                                                                                                                                           |                  |
| `ABR_APP__INIT_ROOT_PASSWORD` | Sets the initial password of the root user when first launching ABR. Has no effect if a root admin already exists.                                                                                                                                           | us               |
| `ABR_DB__USE_POSTGRES`        | Whether to use Postgres as a database. Ensure the connection settings are valid.                                                                                                                                                                             | false            |
| `ABR_DB__POSTGRES_HOST`       | Host URL/IP of the postgres instance.                                                                                                                                                                                                                        | localhost        |
| `ABR_DB__POSTGRES_PORT`       | Port of the postgres instance.                                                                                                                                                                                                                               | 5432             |
| `ABR_DB__POSTGRES_DB`         | Database name of the postgres instance.                                                                                                                                                                                                                      | audiobookrequest |
| `ABR_DB__POSTGRES_USER`       | Username of the postgres database.                                                                                                                                                                                                                           | abr              |
| `ABR_DB__POSTGRES_PASSWORD`   | Password of the postgres database.                                                                                                                                                                                                                           | password         |
| `ABR_DB__POSTGRES_SSL_MODE`   | [SSL mode](https://www.postgresql.org/docs/18/libpq-connect.html#LIBPQ-CONNECT-SSLMODE) to use for the postgres instance.                                                                                                                                    | prefer           |

---

# Contributing

Please read the [contribution guidelines](?tab=contributing-ov-file) before contributing.

## Conventional Commits

This project uses [Conventional Commits](https://www.conventionalcommits.org) to allow for a more organized commit history and support automated changelog generation. Pull requests will be squashed in most cases (with some exceptions).

## Local Development

**NOTE**: If you use VSCode, you can also open up the project with the given dev container settings and then follow the instructions below to get everything set up correctly.

Python virtual environments help isolate any installed packages to this directory. Project was made with `Python 3.12` and uses new generics introduced in 3.12. Older python versions might not work or could have incorrect typing.

For improved dependency management, `uv` is used instead of `pip`.

```sh
# This creates the venv as well as installs all dependencies
uv sync
```

For local development, environment variables can be added to `.env.local` and they'll be used wherever required.

## Initialize Database

[Alembic](https://alembic.sqlalchemy.org/en/latest/) is used to create database migrations. Run the following before starting up the application for the first time. It will initialize the directory if non-existant, create the database file as well as execute any required migrations.

```sh
just alembic_upgrade # or simply 'just au'
# or if you don't have 'just':
uv run alembic upgrade heads
```

_In case of any model changes, remember to create migrations using `alembic revision --autogenerate -m "<message>"`. Note that alembic ALTER table migrations leave out unique constraints for postgres, so those have to be added manually._

## Running

Running the application is best done in multiple terminals:

1. Start FastAPI dev mode:

```sh
just dev # or simply 'just d'
# or if you don't have 'just':
uv run fastapi dev
```

Website can be visited at http://localhost:8000.

2. Tailwind is used in combination with [DaisyUI](https://daisyui.com). Download the source files using the following commands:

```sh
just install_daisy
# or manually
curl -sLo static/daisyui.mjs https://github.com/saadeghi/daisyui/releases/latest/download/daisyui.mjs
curl -sLo static/daisyui-theme.mjs https://github.com/saadeghi/daisyui/releases/latest/download/daisyui-theme.mjs
```

3. Start Tailwindcss watcher. Required for any CSS styling.

```sh
just tailwind # or simply 'just tw'

tailwindcss -i static/tw.css -o static/globals.css --watch
# Alternatively npx can be used to run tailwindcss
npx @tailwindcss/cli@4 -i static/tw.css -o static/globals.css --watch
```

**NOTE**: Website has to be visited at http://localhost:3000 instead.

## Docker Compose

The docker compose can also be used to run the app locally:

```bash
docker compose --profile local up --build
```

# Docs

[Hugo](https://gohugo.io) is used to generate the docs page. It can be found in the `/docs` directory.

# Tools

AudioBookRequest builds on top of a some other great tools. A big thanks goes out to these developers.

- [Audimeta](https://github.com/Vito0912/AudiMeta) - Main audiobook metadata provider. Active in development and quick to fix issues.
- [Audnexus](https://github.com/laxamentumtech/audnexus) - Backup audiobook metadata provider.
- [Prowlarr](https://github.com/Prowlarr/Prowlarr) - Does a lot of the heavy lifting concerning searching through indexers and forwarding download requests to download clients. Saves me the ordeal of having to reimplement everything again.
- [External Audible API](https://audible.readthedocs.io/en/latest/misc/external_api.html) - Audible exposes key API endpoints which are used to, for example, search for books.
