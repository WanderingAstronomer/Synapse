#!/usr/bin/env bash
set -e

# Navigate to project root
cd "$(dirname "$0")/.."

# Determine docker command (handle sg docker if needed)
DOCKER_CMD="docker compose"
if ! docker ps >/dev/null 2>&1; then
    if sg docker -c "docker ps" >/dev/null 2>&1; then
        DOCKER_CMD="sg docker -c 'docker compose"
    fi
fi

echo "🚀 Starting Synapse stack..."
if [ "$DOCKER_CMD" = "docker compose" ]; then
    if ! docker compose up -d --build --wait; then
        echo "❌ Failed to start or services did not become healthy."
        echo "Run 'docker compose logs' to investigate."
        exit 1
    fi
else
    if ! sg docker -c "docker compose up -d --build --wait"; then
        echo "❌ Failed to start or services did not become healthy."
        echo "Run 'sg docker -c \"docker compose logs\"' to investigate."
        exit 1
    fi
fi

# Extract config values safely using Python
COMMUNITY_NAME=$(uv run python -c 'import yaml; print(yaml.safe_load(open("config.yaml")).get("community_name", "Synapse"))' 2>/dev/null || echo "Synapse")
DASHBOARD_URL=$(uv run python -c 'import yaml; print(yaml.safe_load(open("config.yaml")).get("dashboard_url", ""))' 2>/dev/null || echo "")

if [ -z "$DASHBOARD_URL" ] || [ "$DASHBOARD_URL" == "None" ]; then
    DASHBOARD_URL=""
fi

# ---------------------------------------------------------------------------
# Banner status helper
# printf doesn't account for emoji being 2 terminal columns wide.
# Formula: ║(1) + space(1) + label %-13s(13) + space(1) + emoji(2 visual/1 bash)
#          + space(1) + text %-49s(49) + space(1) + ║(1) = 70 visual cols.
# ---------------------------------------------------------------------------
banner_status() {
    local label="$1"
    local ok="$2"
    local icon text
    if [ "$ok" = "1" ]; then icon="🟢"; text="Ready"; else icon="🔴"; text="Unavailable"; fi
    printf "║ %-13s %s %-49s ║\n" "$label" "$icon" "$text"
}

# Database — ask pg_isready inside the container
if docker compose exec -T db pg_isready -U synapse -q 2>/dev/null; then DB_OK=1; else DB_OK=0; fi

# API — hit the health endpoint
if curl -sf --max-time 3 http://localhost:8000/api/health >/dev/null 2>&1; then API_OK=1; else API_OK=0; fi

# Dashboard — HTTP 200 from the SvelteKit server
if curl -sf --max-time 3 http://localhost:3000 >/dev/null 2>&1; then DASH_OK=1; else DASH_OK=0; fi

# Bot — inspect Docker health status
BOT_HEALTH=$(docker compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null | awk '/^bot / {print $2}')
if [ "$BOT_HEALTH" = "healthy" ]; then BOT_OK=1; else BOT_OK=0; fi

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║ SYNAPSE — Ready for Service                                        ║"
printf "║ Community: %-55s ║\n" "$COMMUNITY_NAME"
echo "╠════════════════════════════════════════════════════════════════════╣"
printf "║ %-13s %-52s ║\n" "Dashboard:" "http://localhost:3000 (local)"
if [ -n "$DASHBOARD_URL" ]; then
    printf "║ %-13s %-52s ║\n" "" "$DASHBOARD_URL (external)"
fi
printf "║ %-13s %-52s ║\n" "API Docs:" "http://localhost:8000/docs"
echo "╠════════════════════════════════════════════════════════════════════╣"
banner_status "Database:" $DB_OK
banner_status "API:" $API_OK
banner_status "Dashboard:" $DASH_OK
banner_status "Bot:" $BOT_OK
echo "╠════════════════════════════════════════════════════════════════════╣"
printf "║ %-13s %-52s ║\n" "Logs:" "docker compose logs -f"
printf "║ %-13s %-52s ║\n" "Bot Logs:" "docker compose logs -f bot"
printf "║ %-13s %-52s ║\n" "Stop:" "docker compose down"
printf "║ %-13s %-52s ║\n" "Status:" "docker compose ps"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""
