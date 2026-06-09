#!/bin/sh
set -e

PORT=${PORT:-8081}
INTERVAL=${REFRESH_MINUTES:-15}
HERMES_ENV=/root/.hermes/.env

echo "NOC Dashboard 1 starting..."
echo "  Port: $PORT  Regen: every ${INTERVAL}m"

# Create ~/.hermes/.env from Docker/Portainer env vars so the generator finds them
mkdir -p /root/.hermes
python3 -c "
import os
lines = []
for k, v in sorted(os.environ.items()):
    if not k.replace('_','').replace('-','').isalnum():
        continue
    lines.append(f'{k}={v}')
with open('$HERMES_ENV', 'w') as f:
    f.write('\n'.join(lines) + '\n')
print(f'Wrote {len(lines)} vars to $HERMES_ENV')
"

mkdir -p /app/output

# Initial generation
echo "$(date '+%Y-%m-%d %H:%M:%S') generating..."
HERMES_ENV=$HERMES_ENV NOC_OUT_DIR=/app/output NOC_OUT_FILE=/app/output/index.html \
    python3 /app/generate_dashboard.py || echo "Generation error (non-fatal)"

# Start HTTP server
cd /app/output
python3 -m http.server "$PORT" --bind 0.0.0.0 &
HTTP_PID=$!
echo "HTTP PID: $HTTP_PID"

# Regen loop
while true; do
    sleep "${INTERVAL}m"
    echo "$(date '+%Y-%m-%d %H:%M:%S') regenerating..."
    HERMES_ENV=$HERMES_ENV NOC_OUT_DIR=/app/output NOC_OUT_FILE=/app/output/index.html \
        python3 /app/generate_dashboard.py || echo "Generator error (non-fatal)"
done
