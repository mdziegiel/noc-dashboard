#!/bin/sh
set -e

PORT=${PORT:-8081}
INTERVAL=${REFRESH_MINUTES:-15}
HERMES_ENV=/root/.hermes/.env

echo "NOC Dashboard 2 starting..."
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

# Write the custom HTTP server
cat > /app/server.py << 'PYEOF'
#!/usr/bin/env python3
"""
NOC 2 HTTP server — serves /app/output as static files.
POST /save-layout   — persist card drag order
POST /regenerate    — trigger immediate regen
POST /save-config   — write credential k/v pairs to .env, trigger regen
POST /test-connection — run a collector with provided creds, return state
"""
import http.server, json, os, subprocess, threading, sys, importlib.util, ssl

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

OUTPUT_DIR  = "/app/output"
LAYOUT_FILE = os.path.join(OUTPUT_DIR, "layout.json")
ENV_FILE    = "/root/.hermes/.env"
GENERATOR   = "/app/generate_dashboard.py"
CUSTOM_CARDS_FILE = os.path.join(OUTPUT_DIR, "custom_cards.json")

# ── env helpers ────────────────────────────────────────────────────────────────

def read_env():
    d = {}
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.rstrip('\n')
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    d[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return d

def write_env(d):
    lines = [f"{k}={v}" for k, v in sorted(d.items())]
    with open(ENV_FILE, 'w') as f:
        f.write('\n'.join(lines) + '\n')

# ── regen helper ───────────────────────────────────────────────────────────────

def _run_regen():
    try:
        subprocess.run(
            ["python3", GENERATOR],
            env={**os.environ,
                 "HERMES_ENV": ENV_FILE,
                 "NOC_OUT_DIR": OUTPUT_DIR,
                 "NOC_OUT_FILE": os.path.join(OUTPUT_DIR, "index.html")},
            timeout=120
        )
        print("Regen complete")
    except Exception as e:
        print(f"Regen error: {e}")

# ── collector test ─────────────────────────────────────────────────────────────
# Integration type → which collector function to call and required env keys

COLLECTOR_MAP = {
    "proxmox":      ("collect_proxmox",   ["PROXMOX_HOST", "PROXMOX_TOKEN_ID", "PROXMOX_TOKEN_SECRET"]),
    "docker":       ("collect_docker",    ["PORTAINER_URL", "PORTAINER_USERNAME", "PORTAINER_PASSWORD"]),
    "pbs":          ("collect_pbs",       ["PBS_URL", "PBS_USERNAME", "PBS_PASSWORD"]),
    "kuma":         ("collect_uptime_kuma", ["UPTIME_KUMA_URL", "UPTIME_KUMA_API_KEY"]),
    "crowdsec":     ("collect_crowdsec",  ["CROWDSEC_API_URL", "CROWDSEC_API_KEY"]),
    "wazuh":        ("collect_wazuh",     ["WAZUH_API_URL", "WAZUH_API_USER", "WAZUH_API_PASSWORD"]),
    "unifi":        ("collect_unifi",     ["UNIFI_URL", "UNIFI_USERNAME", "UNIFI_PASSWORD"]),
    "adguard":      ("collect_adguard",   ["ADGUARD_URL", "ADGUARD_USERNAME", "ADGUARD_PASSWORD"]),
    "adguard2":     ("collect_adguard2",  ["ADGUARD2_URL", "ADGUARD2_USERNAME", "ADGUARD2_PASSWORD"]),
    "urbackup":     ("collect_urbackup",  ["URBACKUP_URL", "URBACKUP_USERNAME", "URBACKUP_PASSWORD"]),
    "homeassistant":("collect_homeassistant", ["HASS_URL", "HASS_TOKEN"]),
    "cloudflare":   ("collect_cloudflare",["CLOUDFLARE_TOKEN", "CLOUDFLARE_ZONE_ID"]),
    "npm":          ("collect_npm",       ["NPM_URL", "NPM_EMAIL", "NPM_PASSWORD"]),
    "tailscale":    ("collect_tailscale", ["TAILSCALE_API_KEY"]),
    "limacharlie":  ("collect_limacharlie", ["LIMACHARLIE_OID", "LIMACHARLIE_API_KEY"]),
    "plex":         ("collect_plex",      ["PLEX_URL", "PLEX_TOKEN"]),
    "tautulli":     ("collect_tautulli",  ["TAUTULLI_URL", "TAUTULLI_API_KEY"]),
    "sonarr":       ("collect_sonarr",    ["SONARR_URL", "SONARR_API_KEY"]),
    "radarr":       ("collect_radarr",    ["RADARR_URL", "RADARR_API_KEY"]),
    "lidarr":       ("collect_lidarr",    ["LIDARR_URL", "LIDARR_API_KEY"]),
    "sabnzbd":      ("collect_sabnzbd",   ["SABNZBD_URL", "SABNZBD_API_KEY"]),
    "overseerr":    ("collect_overseerr", ["OVERSEERR_URL", "OVERSEERR_API_KEY"]),
    "prowlarr":     ("collect_prowlarr",  ["PROWLARR_URL", "PROWLARR_API_KEY"]),
    "wgdashboard":  ("collect_wgdashboard", ["WG_URL", "WG_USERNAME", "WG_PASSWORD"]),
    "hyperv":       ("collect_hyperv",    ["HYPERV_HOST", "HYPERV_USERNAME", "HYPERV_PASSWORD"]),
    "qnap":         ("collect_qnaps",     ["QNAP1_HOST", "QNAP_USERNAME", "QNAP_PASSWORD"]),
}

# Field metadata for the UI
FIELD_DEFS = {
    "PROXMOX_HOST":        {"label": "Host (https://ip:port)",  "type": "text"},
    "PROXMOX_TOKEN_ID":    {"label": "Token ID (user@pam!name)","type": "text"},
    "PROXMOX_TOKEN_SECRET":{"label": "Token Secret",            "type": "password"},
    "PORTAINER_URL":       {"label": "URL (https://ip:port)",   "type": "text"},
    "PORTAINER_USERNAME":  {"label": "Username",                "type": "text"},
    "PORTAINER_PASSWORD":  {"label": "Password",                "type": "password"},
    "PBS_URL":             {"label": "URL (https://ip:port)",   "type": "text"},
    "PBS_USERNAME":        {"label": "Username",                "type": "text"},
    "PBS_PASSWORD":        {"label": "Password",                "type": "password"},
    "UPTIME_KUMA_URL":     {"label": "URL (http://ip:port)",    "type": "text"},
    "UPTIME_KUMA_API_KEY": {"label": "API Key",                 "type": "password"},
    "CROWDSEC_API_URL":    {"label": "API URL (http://ip:port)","type": "text"},
    "CROWDSEC_API_KEY":    {"label": "API Key",                 "type": "password"},
    "WAZUH_API_URL":       {"label": "API URL (https://ip:port)","type":"text"},
    "WAZUH_API_USER":      {"label": "Username",                "type": "text"},
    "WAZUH_API_PASSWORD":  {"label": "Password",                "type": "password"},
    "UNIFI_URL":           {"label": "URL (https://ip)",        "type": "text"},
    "UNIFI_USERNAME":      {"label": "Username",                "type": "text"},
    "UNIFI_PASSWORD":      {"label": "Password",                "type": "password"},
    "ADGUARD_URL":         {"label": "URL (http://ip:port)",    "type": "text"},
    "ADGUARD_USERNAME":    {"label": "Username",                "type": "text"},
    "ADGUARD_PASSWORD":    {"label": "Password",                "type": "password"},
    "ADGUARD2_URL":        {"label": "URL (http://ip:port)",    "type": "text"},
    "ADGUARD2_USERNAME":   {"label": "Username",                "type": "text"},
    "ADGUARD2_PASSWORD":   {"label": "Password",                "type": "password"},
    "URBACKUP_URL":        {"label": "URL (http://ip:port)",    "type": "text"},
    "URBACKUP_USERNAME":   {"label": "Username",                "type": "text"},
    "URBACKUP_PASSWORD":   {"label": "Password",                "type": "password"},
    "HASS_URL":            {"label": "URL (http://ip:port)",    "type": "text"},
    "HASS_TOKEN":          {"label": "Long-lived Token",        "type": "password"},
    "CLOUDFLARE_TOKEN":    {"label": "API Token",               "type": "password"},
    "CLOUDFLARE_ZONE_ID":  {"label": "Zone ID",                 "type": "text"},
    "NPM_URL":             {"label": "URL (http://ip:port)",    "type": "text"},
    "NPM_EMAIL":           {"label": "Email",                   "type": "text"},
    "NPM_PASSWORD":        {"label": "Password",                "type": "password"},
    "TAILSCALE_API_KEY":   {"label": "API Key",                 "type": "password"},
    "LIMACHARLIE_OID":     {"label": "Organization ID",         "type": "text"},
    "LIMACHARLIE_API_KEY": {"label": "API Key",                 "type": "password"},
    "PLEX_URL":            {"label": "URL (http://ip:port)",    "type": "text"},
    "PLEX_TOKEN":          {"label": "Token",                   "type": "password"},
    "TAUTULLI_URL":        {"label": "URL (http://ip:port)",    "type": "text"},
    "TAUTULLI_API_KEY":    {"label": "API Key",                 "type": "password"},
    "SONARR_URL":          {"label": "URL (http://ip:port)",    "type": "text"},
    "SONARR_API_KEY":      {"label": "API Key",                 "type": "password"},
    "RADARR_URL":          {"label": "URL (http://ip:port)",    "type": "text"},
    "RADARR_API_KEY":      {"label": "API Key",                 "type": "password"},
    "LIDARR_URL":          {"label": "URL (http://ip:port)",    "type": "text"},
    "LIDARR_API_KEY":      {"label": "API Key",                 "type": "password"},
    "SABNZBD_URL":         {"label": "URL (http://ip:port)",    "type": "text"},
    "SABNZBD_API_KEY":     {"label": "API Key",                 "type": "password"},
    "OVERSEERR_URL":       {"label": "URL (http://ip:port)",    "type": "text"},
    "OVERSEERR_API_KEY":   {"label": "API Key",                 "type": "password"},
    "PROWLARR_URL":        {"label": "URL (http://ip:port)",    "type": "text"},
    "PROWLARR_API_KEY":    {"label": "API Key",                 "type": "password"},
    "WG_URL":              {"label": "URL (http://ip:port)",    "type": "text"},
    "WG_USERNAME":         {"label": "Username",                "type": "text"},
    "WG_PASSWORD":         {"label": "Password",                "type": "password"},
    "HYPERV_HOST":         {"label": "Host IP",                 "type": "text"},
    "HYPERV_USERNAME":     {"label": "Username",                "type": "text"},
    "HYPERV_PASSWORD":     {"label": "Password",                "type": "password"},
    "QNAP1_HOST":          {"label": "NAS1 URL (http://ip:port)","type":"text"},
    "QNAP2_HOST":          {"label": "NAS2 URL (optional)",     "type": "text"},
    "QNAP3_HOST":          {"label": "NAS3 URL (optional)",     "type": "text"},
    "QNAP_USERNAME":       {"label": "Username",                "type": "text"},
    "QNAP_PASSWORD":       {"label": "Password",                "type": "password"},
}

_gen_module = None

def _load_generator():
    global _gen_module
    if _gen_module is not None:
        return _gen_module
    spec = importlib.util.spec_from_file_location("gen", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _gen_module = mod
    return mod


class NOCHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OUTPUT_DIR, **kwargs)

    def log_message(self, fmt, *args):
        pass

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/integration-fields":
            # Return field defs for the UI
            result = {}
            for itype, (fn_name, keys) in COLLECTOR_MAP.items():
                result[itype] = [
                    {"key": k, **FIELD_DEFS.get(k, {"label": k, "type": "text"})}
                    for k in keys
                ]
            self.send_json(200, result)
            return
        if self.path == "/api/custom-cards":
            # Return saved custom card configs
            try:
                with open(CUSTOM_CARDS_FILE) as f:
                    data = f.read()
            except FileNotFoundError:
                data = "[]"
            except Exception:
                data = "[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode())
            return
        if self.path == "/api/current-config":
            # Return current env values (masked for passwords)
            e = read_env()
            masked = {}
            for k, v in e.items():
                if any(kw in k.lower() for kw in ("password", "token", "secret", "key")):
                    masked[k] = "••••••••" if v else ""
                else:
                    masked[k] = v
            self.send_json(200, masked)
            return
        super().do_GET()

    def do_POST(self):
        if self.path == "/save-layout":
            try:
                layout = self.read_body()
                with open(LAYOUT_FILE, "w") as f:
                    json.dump(layout, f, indent=2)
                self.send_json(200, {"ok": True})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif self.path == "/regenerate":
            threading.Thread(target=_run_regen, daemon=True).start()
            self.send_json(202, {"ok": True, "msg": "regenerating"})

        elif self.path == "/save-config":
            # Receive {key: value} pairs, merge into .env, trigger regen
            try:
                payload = self.read_body()
                if not isinstance(payload, dict):
                    self.send_json(400, {"error": "expected object"})
                    return
                e = read_env()
                changed = []
                for k, v in payload.items():
                    if k and isinstance(k, str) and k.replace('_','').isalnum():
                        if str(v).strip():  # only set non-empty values
                            e[k] = str(v).strip()
                            changed.append(k)
                write_env(e)
                print(f"Config saved: {changed}")
                threading.Thread(target=_run_regen, daemon=True).start()
                self.send_json(200, {"ok": True, "saved": changed, "regen": True})
            except Exception as e2:
                self.send_json(500, {"error": str(e2)})

        elif self.path == "/test-connection":
            # Run collector with provided creds, return result
            try:
                payload = self.read_body()
                itype = payload.get("type", "")
                creds = payload.get("creds", {})  # {ENV_KEY: value, ...}

                if itype not in COLLECTOR_MAP:
                    self.send_json(400, {"error": f"unknown integration: {itype}"})
                    return

                fn_name, required_keys = COLLECTOR_MAP[itype]

                # Build temp env: current .env + provided creds
                e = read_env()
                e.update({k: v for k, v in creds.items() if v})

                # Load generator and call the collector
                try:
                    gen = _load_generator()
                    # Patch gen.E with our temp env for this call
                    orig_E = gen.E.copy()
                    gen.E.update(e)
                    try:
                        fn = getattr(gen, fn_name)
                        result = fn()
                    finally:
                        gen.E.clear()
                        gen.E.update(orig_E)

                    ok = result.get("state") == "ok"
                    self.send_json(200, {
                        "ok": ok,
                        "state": result.get("state"),
                        "note": result.get("note") or result.get("error") or "",
                        "detail": {k: v for k, v in result.items()
                                   if k not in ("state", "note", "error") and not isinstance(v, (list, dict))}
                    })
                except Exception as ce:
                    self.send_json(200, {"ok": False, "state": "error", "note": str(ce)[:200]})

            except Exception as e2:
                self.send_json(500, {"error": str(e2)})

        elif self.path == "/save-custom-cards":
            # Receive list of custom card configs, persist to disk
            try:
                payload = self.read_body()
                if not isinstance(payload, list):
                    self.send_json(400, {"error": "expected array"})
                    return
                import json as _json
                with open(CUSTOM_CARDS_FILE, "w") as f:
                    _json.dump(payload, f, indent=2)
                self.send_json(200, {"ok": True, "count": len(payload)})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif self.path == "/api/fetch-custom":
            # Proxy fetch for custom cards — runs server-side so no CORS issues
            import urllib.request as _ureq
            import base64 as _b64mod
            try:
                payload = self.read_body()
                url        = payload.get("url", "")
                auth_type  = payload.get("auth_type", "none")
                auth_value = payload.get("auth_value", "")
                auth_key_header = payload.get("auth_key_header", "X-API-Key")
                auth_user  = payload.get("auth_user", "")
                auth_pass  = payload.get("auth_pass", "")
                oauth_token_url     = payload.get("oauth_token_url", "")
                oauth_client_id     = payload.get("oauth_client_id", "")
                oauth_client_secret = payload.get("oauth_client_secret", "")
                oauth_scope         = payload.get("oauth_scope", "")

                if not url:
                    self.send_json(400, {"ok": False, "error": "no url"})
                    return

                headers = {}
                if auth_type == "bearer" and auth_value:
                    headers["Authorization"] = "Bearer " + auth_value
                elif auth_type == "apikey" and auth_value:
                    headers[auth_key_header or "X-API-Key"] = auth_value
                elif auth_type == "basic":
                    creds = _b64mod.b64encode((auth_user + ":" + auth_pass).encode()).decode()
                    headers["Authorization"] = "Basic " + creds
                elif auth_type == "oauth" and oauth_token_url:
                    # Client credentials grant
                    try:
                        import urllib.parse as _uparse
                        token_data = _uparse.urlencode({
                            "grant_type": "client_credentials",
                            "client_id": oauth_client_id,
                            "client_secret": oauth_client_secret,
                            "scope": oauth_scope,
                        }).encode()
                        token_req = _ureq.Request(
                            oauth_token_url,
                            data=token_data,
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                        )
                        with _ureq.urlopen(token_req, timeout=10, context=CTX) as tr:
                            token_resp = json.loads(tr.read().decode("utf-8", "replace"))
                        access_token = token_resp.get("access_token", "")
                        if access_token:
                            headers["Authorization"] = "Bearer " + access_token
                    except Exception as oe:
                        self.send_json(200, {"ok": False, "error": "OAuth token error: " + str(oe)[:120]})
                        return

                req = _ureq.Request(url, headers=headers)
                try:
                    with _ureq.urlopen(req, timeout=15, context=CTX) as resp:
                        raw = resp.read().decode("utf-8", "replace")
                except Exception as fe:
                    self.send_json(200, {"ok": False, "error": str(fe)[:200]})
                    return

                parsed = None
                try:
                    parsed = json.loads(raw)
                except Exception:
                    pass

                self.send_json(200, {"ok": True, "raw": raw[:500], "json": parsed})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), NOCHandler)
    print(f"NOC2 HTTP server on port {port}")
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
