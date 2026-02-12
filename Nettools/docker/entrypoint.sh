#!/bin/bash
# =========================================
#  NetTools - Container Entrypoint
#  Starts backend (uvicorn) + frontend (nginx)
# =========================================

set -e

echo "============================================"
echo "  NetTools - Starting..."
echo "============================================"

# Ensure data directory exists
mkdir -p /data

# Start nginx in background
echo "[NetTools] Starting Nginx..."
nginx -g 'daemon on;'

# Verify Ookla Speedtest CLI
if speedtest --version 2>&1 | grep -qi "ookla"; then
    echo "[NetTools] Ookla Speedtest CLI: OK"
else
    echo "[NetTools] WARNING: Ookla Speedtest CLI not found, using Python fallback"
fi

echo "[NetTools] Starting Backend (uvicorn)..."
echo "[NetTools] Ready at http://localhost:8080"
echo "============================================"

# Start uvicorn in foreground (main process)
exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
