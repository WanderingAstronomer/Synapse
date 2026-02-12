# 08 — Deployment & Infrastructure

> *If it can't run with `docker compose up`, it isn't done.*

---

## 8.1 Environments

| Environment | Purpose | Database | Bot Token | URL |
|-------------|---------|----------|-----------|-----|
| **Local** | Development | Docker container (localhost:5432) | Dev bot token | localhost:5173 (dashboard), localhost:8000 (API) |
| **Staging** | Pre-production testing | Azure PG Flexible (Burstable) | Staging bot token | staging.synapse.club |
| **Production** | Live deployment | Azure PG Flexible (General) | Production bot token | synapse.club |

---

## 8.2 Local Development Stack (Docker Compose)

Four services, one network, one volume:

```yaml
services:
  db:         # PostgreSQL 16
  bot:        # python -m synapse.bot
  api:        # uvicorn synapse.api.main:app --host 0.0.0.0 --port 8000
  dashboard:  # node build (SvelteKit adapter-node)
```

### Service Details

| Service | Build | Port | Depends On | Restart |
|---------|-------|------|-----------|----------|
| `db` | `postgres:16-alpine` | 5432 | — | unless-stopped |
| `bot` | `Dockerfile` | — (no port) | db (healthy) | unless-stopped |
| `api` | `Dockerfile` | 8000 | db (healthy) | unless-stopped |
| `dashboard` | `dashboard/Dockerfile` | 3000 | api | unless-stopped |

### Compose Watch (Live Reload)

Docker Compose Watch is configured so code changes sync to running containers
without a full rebuild:

- **Code changes** (`synapse/`, `config.yaml`) → `action: sync` (instant).
- **Dependency changes** (`pyproject.toml`) → `action: rebuild` (full rebuild).

### Quick Commands

```bash
# Full stack
docker compose up --build

# Just the database (bot runs locally via uv)
docker compose up db -d

# Rebuild after dependency change
docker compose up --build bot api dashboard

# View logs
docker compose logs -f bot
docker compose logs -f dashboard
docker compose logs -f api

# Tear down (preserves data volume)
docker compose down

# Tear down AND delete data
docker compose down -v
```

---

## 8.3 Dockerfiles

### Python Services (Bot + API) — Multi-Stage

The Dockerfile uses a two-stage build optimized for `uv`:

### Stage 1: Builder

```
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

# Then copy source and install project
COPY . .
RUN uv sync --locked --no-dev --no-editable
```

### Stage 2: Runtime

```
FROM python:3.12-slim
COPY --from=builder /app/.venv /app/.venv
COPY . /app
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "synapse.bot"]
```

**Optimization notes:**
- `UV_COMPILE_BYTECODE=1` — Pre-compiles `.pyc` files for faster startup.
- `UV_LINK_MODE=copy` — Required when cache and target are on different
  filesystems.
- Cache mounts (`--mount=type=cache,target=/root/.cache/uv`) — Reuses
  downloaded packages across builds.

### Dashboard (SvelteKit) — Multi-Stage

The dashboard has its own Dockerfile (`dashboard/Dockerfile`) using a
Node.js 22 multi-stage build:

```
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=builder /app/build ./build
COPY --from=builder /app/package*.json ./
RUN npm ci --omit=dev
ENV PORT=3000
CMD ["node", "build"]
```

The SvelteKit adapter-node produces a standalone Node.js server.

---

## 8.4 Azure Production Architecture

### Resource Group: `synapse-prod`

```
Azure Resource Group: synapse-prod
│
├── Azure Container Registry (synapse.azurecr.io)
│   └── Stores Docker images for all services
│
├── App Service Plan (B1 Linux — shared plan)
│   ├── App Service: synapse-bot
│   │   └── Docker: python -m synapse.bot
│   │   └── Always On: Yes (bot must stay connected)
│   │
│   ├── App Service: synapse-api
│   │   └── Docker: uvicorn synapse.api.main:app
│   │   └── Custom domain: api.synapse.club
│   │
│   └── App Service: synapse-dashboard
│       └── Docker: node build (SvelteKit)
│       └── Custom domain: synapse.club
│
├── PostgreSQL Flexible Server (Burstable B1ms)
│   └── Database: synapse
│   └── Firewall: Allow Azure services only
│   └── SSL: Required
│
└── Key Vault: synapse-secrets
    ├── DISCORD-TOKEN
    ├── DATABASE-URL
    ├── JWT-SECRET
    └── LLM-API-KEY (future)
```

### Cost Estimate (Monthly)

| Resource | SKU | Est. Cost |
|----------|-----|-----------|
| App Service Plan | B1 (1 core, 1.75 GB) | ~$13 |
| PostgreSQL Flexible | Burstable B1ms | ~$16 |
| Container Registry | Basic | ~$5 |
| Key Vault | Standard | ~$0.03/secret/month |
| **Total** | | **~$34/month** |

---

## 8.5 CI/CD Pipeline (GitHub Actions)

### Trigger

On push to `main` branch, or manual dispatch.

### Pipeline

```yaml
name: Deploy Synapse

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      # 1. Checkout
      - uses: actions/checkout@v4

      # 2. Login to Azure Container Registry
      - uses: azure/docker-login@v2
        with:
          login-server: synapse.azurecr.io
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      # 3. Build and push images
      - run: |
          docker build -t synapse.azurecr.io/synapse:${{ github.sha }} .
          docker push synapse.azurecr.io/synapse:${{ github.sha }}

      # 4. Deploy to App Services
      - uses: azure/webapps-deploy@v3
        with:
          app-name: synapse-bot
          images: synapse.azurecr.io/synapse:${{ github.sha }}

      # Repeat for dashboard service
```

### Secrets Required in GitHub

| Secret | Source |
|--------|--------|
| `ACR_USERNAME` | Azure Container Registry admin username |
| `ACR_PASSWORD` | Azure Container Registry admin password |
| `AZURE_CREDENTIALS` | Service principal JSON for Azure login |

---

## 8.6 Configuration Management

### Local Dev

Secrets: `.env` file (gitignored).
Soft config: `config.yaml` (committed).
Zone/Achievement config: PostgreSQL rows (seeded from `seed.py`).

### Production

Secrets: Azure Key Vault → injected as App Service environment variables.
Soft config: `config.yaml` baked into the Docker image.
Zone/Achievement config: PostgreSQL rows (managed via Admin Panel).

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Bot authentication token |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `DISCORD_CLIENT_ID` | Yes | OAuth2 application client ID |
| `DISCORD_CLIENT_SECRET` | Yes | OAuth2 application client secret |
| `DISCORD_REDIRECT_URI` | Yes | OAuth2 callback URL (e.g., `http://localhost:5173/auth/callback`) |
| `JWT_SECRET` | Yes | HMAC-SHA256 signing key for admin JWTs (`openssl rand -hex 32`) |
| `FRONTEND_URL` | Yes | Dashboard base URL (e.g., `http://localhost:5173`) |
| `DEV_GUILD_ID` | No | Guild ID for instant slash command sync (dev only) |
| `LLM_API_KEY` | No | API key for LLM quality assessment (future) |
| `ADMIN_ROLE_ID` | No | Discord role ID required for admin commands |

---

## 8.7 Monitoring & Observability (Future)

| Tool | Purpose |
|------|---------|
| Azure Monitor | App Service health, CPU, memory |
| Application Insights | Request tracing, error logging |
| PostgreSQL Metrics | Query performance, connection count |
| Custom Dashboard Tab | Bot uptime, events/minute, error rate |

---

## Decisions

> **Decision D08-01:** Separate Dockerfiles for Python and Node Services
> - **Status:** Accepted (Amended v3.0)
> - **Context:** Bot and API share the same Python Dockerfile, but the
>   SvelteKit dashboard requires a Node.js build environment.
> - **Choice:** One Python Dockerfile (different `CMD` overrides for bot
>   and API) plus a separate `dashboard/Dockerfile` for the Node.js build.
> - **Consequences:** Two Docker images in the registry.  Clean separation
>   between Python and Node.js build pipelines.

> **Decision D08-02:** Azure App Service Over AKS
> - **Status:** Accepted
> - **Context:** Kubernetes (AKS) is overkill for 3-4 containers.
> - **Choice:** Azure App Service with Docker containers.
> - **Consequences:** Simpler ops, lower cost, no K8s expertise required.
>   Can migrate to AKS later if scale demands it.

> **Decision D08-03:** No Redis (Yet) — PG LISTEN/NOTIFY Instead (Amended v2.2)
> - **Status:** Accepted
> - **Context:** In-memory caching is sufficient at <10k members.  Original
>   5-min TTL was identified as a credibility risk for admin-changed
>   multipliers.
> - **Choice:** No external cache layer.  Zone/multiplier caches live in
>   each process, invalidated via PostgreSQL LISTEN/NOTIFY when the admin
>   service layer commits a config change.  See D05-08.
> - **Consequences:** Near-instant propagation of admin changes.  No Redis
>   dependency.  Bot must run an asyncio listener task on the PG channel.
