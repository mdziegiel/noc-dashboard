#!/bin/sh
set -e

PORT=${PORT:-8081}
INTERVAL=${REFRESH_MINUTES:-15}
HERMES_ENV=/root/.hermes/.env

echo "NOC Dashboard 1 starting..."
echo "  Port: $PORT  Regen: every ${INTERVAL}m"

# Create ~/.hermes/.env from Docker/Portainer env vars
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

# Write the custom HTTP server (supports POST /save-layout)
cat > /app/server.py << 'PYEOF'
#!/usr/bin/env python3
"""
NOC 1 HTTP server — serves /app/output as static files.
Handles POST /save-layout to persist card order.
Handles POST /regenerate to trigger immediate regen.
"""
import http.server
import json
import os
import subprocess
import threading

OUTPUT_DIR = "/app/output"
LAYOUT_FILE = os.path.join(OUTPUT_DIR, "layout.json")

class NOCHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OUTPUT_DIR, **kwargs)

    def log_message(self, fmt, *args):
        # Suppress access logs to keep output clean
        pass

    def do_POST(self):
        if self.path == "/save-layout":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                layout = json.loads(body)
                with open(LAYOUT_FILE, "w") as f:
                    json.dump(layout, f, indent=2)
                print(f"Layout saved: {len(layout)} sections")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                print(f"Save layout error: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        elif self.path == "/regenerate":
            def regen():
                try:
                    subprocess.run(
                        ["python3", "/app/generate_dashboard.py"],
                        env={**os.environ,
                             "HERMES_ENV": "/root/.hermes/.env",
                             "NOC_OUT_DIR": OUTPUT_DIR,
                             "NOC_OUT_FILE": os.path.join(OUTPUT_DIR, "index.html")},
                        timeout=120
                    )
                except Exception as e:
                    print(f"Regen error: {e}")
            threading.Thread(target=regen, daemon=True).start()
            self.send_response(202)
            self.end_headers()
            self.wfile.write(b'{"ok":true,"msg":"regenerating"}')
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), NOCHandler)
    print(f"NOC1 HTTP server on port {port}")
    server.serve_forever()
PYEOF

# Initial generation
echo "$(date '+%Y-%m-%d %H:%M:%S') generating..."
HERMES_ENV=$HERMES_ENV NOC_OUT_DIR=/app/output NOC_OUT_FILE=/app/output/index.html \
    python3 /app/generate_dashboard.py || echo "Generation error (non-fatal)"

# Start custom HTTP server in background
python3 /app/server.py &
HTTP_PID=$!
echo "HTTP PID: $HTTP_PID"

# Regen loop
while true; do
    sleep "${INTERVAL}m"
    echo "$(date '+%Y-%m-%d %H:%M:%S') regenerating..."
    HERMES_ENV=$HERMES_ENV NOC_OUT_DIR=/app/output NOC_OUT_FILE=/app/output/index.html \
        python3 /app/generate_dashboard.py || echo "Generator error (non-fatal)"
done
