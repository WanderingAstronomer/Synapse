# Synapse

A modular community operating system for Discord. Captures activity, drives engagement through a configurable economy, and surfaces insights through a real-time dashboard.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, discord.py
- **Frontend:** SvelteKit 2 (Svelte 5), TypeScript, Tailwind CSS
- **Infrastructure:** Docker Compose, PostgreSQL 16
- **Quality:** pytest, Ruff, mypy

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A Discord bot token ([Developer Portal](https://discord.com/developers/applications))

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/WanderingAstronomer/Synapse.git
   cd Synapse
   ```

2. Copy the environment file and fill in your secrets:
   ```bash
   cp .env.example .env
   ```

3. Start the stack:
   ```bash
   docker compose up -d --build
   ```

4. Open the dashboard at `http://localhost:3000`.

### Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Run linter
uv run ruff check .
```

## Documentation

Comprehensive documentation is available in the `docs/` directory.

- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Self Hosting](docs/SELF_HOSTING.md)
