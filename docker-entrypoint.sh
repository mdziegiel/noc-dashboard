#!/bin/sh
set -e

INTERVAL=${REFRESH_MINUTES:-15}
PORT=${PORT:-8081}
CONFIG=${CONFIG_FILE:-/app/dashboard.yaml}
OUTPUT=/app/output/index.html

echo "NOC Dashboard starting..."
echo "  Config: $CONFIG"
echo "  Refresh: every ${INTERVAL}m"
echo "  Serving on port $PORT"

# Generate on first boot
python3 /app/generator.py --config "$CONFIG" --output "$OUTPUT"

# Start HTTP server in background
cd /app/output
python3 -m http.server "$PORT" --bind 0.0.0.0 &
HTTP_PID=$!

echo "HTTP server PID: $HTTP_PID"

# Cron loop
while true; do
    sleep "${INTERVAL}m"
    echo "$(date) regenerating..."
    python3 /app/generator.py --config "$CONFIG" --output "$OUTPUT" || echo "Generator error (non-fatal)"
done
