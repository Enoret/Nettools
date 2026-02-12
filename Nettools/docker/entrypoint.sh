#!/bin/bash
# =========================================
#  NetTools - Container Entrypoint
#  Starts backend (uvicorn) + frontend (nginx)
# =========================================

set -e

# Default ports if not set
export NETTOOLS_PORT=${NETTOOLS_PORT:-8080}
export NETTOOLS_BACKEND_PORT=${NETTOOLS_BACKEND_PORT:-8000}

echo "============================================"
echo "  NetTools - Starting..."
echo "  Port: ${NETTOOLS_PORT} (backend: ${NETTOOLS_BACKEND_PORT})"
echo "============================================"

# Ensure data directory exists
mkdir -p /data

# Replace port variable in nginx config
envsubst '${NETTOOLS_PORT} ${NETTOOLS_BACKEND_PORT}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Start nginx in background
echo "[NetTools] Starting Nginx on port ${NETTOOLS_PORT}..."
nginx -g 'daemon on;'

# Verify Ookla Speedtest CLI
if speedtest --version 2>&1 | grep -qi "ookla"; then
    echo "[NetTools] Ookla Speedtest CLI: OK"
else
    echo "[NetTools] WARNING: Ookla Speedtest CLI not found, using Python fallback"
fi

echo "[NetTools] Starting Backend (uvicorn)..."
echo "[NetTools] Ready at http://localhost:${NETTOOLS_PORT}"
echo "============================================"

# Start uvicorn in foreground (main process)
exec uvicorn main:app --host 0.0.0.0 --port ${NETTOOLS_BACKEND_PORT} --log-level info
