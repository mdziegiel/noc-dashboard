#!/bin/sh
set -e

PORT=${PORT:-8081}
WORKERS=${WORKERS:-2}

echo "NOC Dashboard starting..."
echo "  FastAPI + React frontend"
echo "  Port: $PORT"
echo "  Workers: $WORKERS"

exec python3 -m uvicorn server:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info
