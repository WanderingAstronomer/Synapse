#!/usr/bin/env bash
set -euo pipefail

cd /app

echo "[synapse] starting API on :8000"
python -m uvicorn synapse.api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "[synapse] starting dashboard on :3000"
cd /app/dashboard
node build &
DASH_PID=$!

cd /app
echo "[synapse] starting Discord bot"
python -m synapse.bot &
BOT_PID=$!

trap 'echo "[synapse] shutting down"; kill ${API_PID} ${DASH_PID} ${BOT_PID} 2>/dev/null || true; wait' SIGINT SIGTERM

wait -n ${API_PID} ${DASH_PID} ${BOT_PID}
EXIT_CODE=$?

echo "[synapse] one process exited (${EXIT_CODE}); stopping others"
kill ${API_PID} ${DASH_PID} ${BOT_PID} 2>/dev/null || true
wait || true
exit ${EXIT_CODE}
