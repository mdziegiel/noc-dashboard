#!/bin/sh
set -e

PORT=${PORT:-8081}
WORKERS=${WORKERS:-2}
STATE_DIR=/app/state
DEFAULT_LAYOUT=/app/default_layout.json

# On first run (empty volume), seed the layout from the baked-in default
mkdir -p "$STATE_DIR"
if [ ! -f "$STATE_DIR/layout.json" ] && [ -f "$DEFAULT_LAYOUT" ]; then
    echo "Seeding layout.json from default..."
    cp "$DEFAULT_LAYOUT" "$STATE_DIR/layout.json"
fi

echo "NOC Dashboard v2 starting..."
echo "  Port: $PORT  Workers: $WORKERS"

exec python3 -m uvicorn server:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info
