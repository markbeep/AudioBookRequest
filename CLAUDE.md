# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Install dependencies using uv
uv sync

# Initialize database (required before first run)
uv run alembic upgrade heads

# Create database migrations after model changes
uv run alembic revision --autogenerate -m "<message>"
```

### Development Server
```bash
# Start FastAPI development server
uv run fastapi dev

# Start Tailwind CSS watcher (in separate terminal)
npm i
uv run tailwindcss -i static/tw.css -o static/globals.css --watch
# Alternative: npx @tailwindcss/cli@4 -i static/tw.css -o static/globals.css --watch

# Optional: Start browser-sync for hot reloading (in separate terminal)
browser-sync http://localhost:8000 --files templates/** --files app/**
# Note: Access via http://localhost:3000 when using browser-sync
```

### Code Quality
```bash
# Type checking
uv run pyright

# Linting and formatting
uv run ruff check
uv run ruff format

# HTML template linting
uv run djlint templates/
```

### Testing
```bash
# Run tests (check for test commands in pyproject.toml or scripts)
# No explicit test framework configured - check with maintainers
```

## Architecture Overview

### Core Structure
- **FastAPI Application**: Main web framework with HTMX frontend
- **SQLModel + Alembic**: Database ORM and migrations
- **Authentication**: Custom session middleware with OIDC support
- **Frontend**: Jinja2 templates with Tailwind CSS + DaisyUI styling

### Key Components

#### Authentication System (`app/internal/auth/`)
- `session_middleware.py`: Custom session management
- `authentication.py`: Auth configuration and user verification
- `oidc_config.py`: OpenID Connect integration
- Three user groups: `untrusted`, `trusted`, `admin`

#### Book Search & Indexing (`app/internal/`)
- `book_search.py`: Search functionality across indexers
- `indexers/`: Abstraction layer for different book sources
- `prowlarr/`: Prowlarr integration for automatic downloads
- `ranking/`: Quality assessment and download ranking algorithms

#### Data Models (`app/internal/models.py`)
- `User`: User accounts with group-based permissions
- `BookRequest`: Request tracking with status management
- All models use SQLModel for type safety

#### Routers (`app/routers/`)
- `auth.py`: Login/logout endpoints
- `root.py`: Main page and wishlist management
- `search.py`: Book search API
- `settings.py`: Admin configuration pages
- `wishlist.py`: Request management

### Database
- SQLite by default (configurable path)
- Alembic migrations in `alembic/versions/`
- Models defined with SQLModel for type safety

### Frontend Architecture
- **Templates**: Jinja2 in `templates/` directory
- **Styling**: Tailwind CSS with DaisyUI components
- **JavaScript**: Alpine.js for interactivity, HTMX for server interactions
- **Icons**: Custom SVG icons in `templates/icons/`

### Configuration
- Environment variables with `ABR_` prefix
- Settings managed through `app/internal/env_settings.py`
- Configuration persisted in `/config` directory (Docker volume)

## Development Notes

### Requirements
- Python 3.12+ (uses new generics syntax)
- uv for dependency management
- Node.js/npm for frontend build tools

### Key Patterns
- Type-safe configuration with Pydantic Settings
- Custom exception handling with redirect responses
- Template fragments for HTMX partial updates
- Group-based authorization decorators

### Environment Variables
Use `.env.local` for local development overrides. Key variables:
- `ABR_APP__DEBUG`: Enable debug mode
- `ABR_APP__CONFIG_DIR`: Data persistence directory
- `ABR_DB__SQLITE_PATH`: Database file location