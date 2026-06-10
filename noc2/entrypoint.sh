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
POST /save-dashboard-config — write branding settings to state/config.json, trigger regen
POST /test-connection — run a collector with provided creds, return state
"""
import http.server, json, os, subprocess, threading, sys, importlib.util, ssl, time, secrets, hashlib, re, base64, hmac, struct, uuid
import urllib.parse
import html
from email.utils import formatdate
import bcrypt

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

OUTPUT_DIR  = "/app/output"
STATE_DIR   = os.environ.get("NOC_STATE_DIR", os.path.join(OUTPUT_DIR, "state"))
LAYOUT_FILE = os.path.join(OUTPUT_DIR, "layout.json")
CONFIG_FILE = os.environ.get("NOC_CONFIG_FILE", os.path.join(STATE_DIR, "config.json"))
ENV_FILE    = "/root/.hermes/.env"
GENERATOR   = "/app/generate_dashboard.py"
CUSTOM_CARDS_FILE = os.path.join(OUTPUT_DIR, "custom_cards.json")
BUILTIN_CARD_CONFIGS_FILE = os.path.join(OUTPUT_DIR, "builtin_card_configs.json")
DEFAULT_DASHBOARD_CONFIG = {
    "dashboard_title": "NOC Dashboard",
    "dashboard_subtitle": "Infrastructure Monitoring",
    "logo_url": "",
    "timezone": "UTC",
    "show_ticker_bar": True,
    "date_format": "YYYY-MM-DD",
    "clock_format": "24hr",
}
AUTH_COOKIE="noc_session"
SESSION_DAYS = 90


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

def read_dashboard_config():
    cfg = dict(DEFAULT_DASHBOARD_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for key in cfg:
                val = raw.get(key)
                if key == "show_ticker_bar":
                    if isinstance(val, bool):
                        cfg[key] = val
                elif isinstance(val, str):
                    cfg[key] = val.strip()
    except FileNotFoundError:
        pass
    cfg["dashboard_title"] = cfg["dashboard_title"] or DEFAULT_DASHBOARD_CONFIG["dashboard_title"]
    cfg["dashboard_subtitle"] = cfg["dashboard_subtitle"] or DEFAULT_DASHBOARD_CONFIG["dashboard_subtitle"]
    cfg["timezone"] = cfg.get("timezone") or "UTC"
    if not isinstance(cfg.get("show_ticker_bar"), bool):
        cfg["show_ticker_bar"] = True
    if cfg.get("date_format") not in ("MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"):
        cfg["date_format"] = "YYYY-MM-DD"
    if cfg.get("clock_format") not in ("12hr", "24hr"):
        cfg["clock_format"] = "24hr"
    return cfg

def write_dashboard_config(payload):
    state = read_state_config()
    cfg = read_dashboard_config()
    for key in cfg:
        val = payload.get(key, "") if isinstance(payload, dict) else ""
        if key == "show_ticker_bar":
            if isinstance(val, bool):
                cfg[key] = val
        elif isinstance(val, str):
            cfg[key] = val.strip()
    cfg["dashboard_title"] = cfg["dashboard_title"] or DEFAULT_DASHBOARD_CONFIG["dashboard_title"]
    cfg["dashboard_subtitle"] = cfg["dashboard_subtitle"] or DEFAULT_DASHBOARD_CONFIG["dashboard_subtitle"]
    cfg["timezone"] = cfg.get("timezone") or "UTC"
    if not isinstance(cfg.get("show_ticker_bar"), bool):
        cfg["show_ticker_bar"] = True
    if cfg.get("date_format") not in ("MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"):
        cfg["date_format"] = "YYYY-MM-DD"
    if cfg.get("clock_format") not in ("12hr", "24hr"):
        cfg["clock_format"] = "24hr"
    state.update(cfg)
    write_state_config(state)
    return cfg

def read_state_config():
    state = dict(DEFAULT_DASHBOARD_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            state.update(raw)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    state["users"] = state.get("users") if isinstance(state.get("users"), list) else []
    state["sessions"] = state.get("sessions") if isinstance(state.get("sessions"), list) else []
    state["login_audit"] = state.get("login_audit") if isinstance(state.get("login_audit"), list) else []
    state["api_tokens"] = state.get("api_tokens") if isinstance(state.get("api_tokens"), list) else []
    if not isinstance(state.get("security_settings"), dict):
        state["security_settings"] = {"password_expiry_enabled": False, "password_expiry_days": 90}
    else:
        state["security_settings"].setdefault("password_expiry_enabled", False)
        state["security_settings"].setdefault("password_expiry_days", 90)
    return state

def write_state_config(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
        f.write(chr(10))
    os.replace(tmp, CONFIG_FILE)

def public_dashboard_config():
    return read_dashboard_config()

def password_error(password):
    if not isinstance(password, str) or len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not (re.search(r"[0-9]", password) or re.search(r"[^A-Za-z0-9]", password)):
        return "Password must include at least one number or symbol."
    return ""

def normalize_username(username):
    return str(username or "").strip()[:64]

def users_exist():
    return bool(read_state_config().get("users"))

def find_user(state, username):
    username = normalize_username(username).lower()
    for user in state.get("users", []):
        if normalize_username(user.get("username")).lower() == username:
            return user
    return None

def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

def verify_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), str(password_hash or "").encode("utf-8"))
    except Exception:
        return False

def new_session(state, username, ip="", user_agent=""):
    token = secrets.token_urlsafe(48)
    now = int(time.time())
    exp = now + SESSION_DAYS * 86400
    state["sessions"] = [s for s in state.get("sessions", []) if int(s.get("expires", 0)) > now]
    state["sessions"].append({
        "id": uuid.uuid4().hex,
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "username": username,
        "created": now,
        "last_activity": now,
        "ip": ip,
        "user_agent": str(user_agent or "")[:240],
        "expires": exp,
    })
    write_state_config(state)
    return token, exp

def cookie_header(token, expires):
    # Max-Age is enough by spec, but Expires makes browser/proxy behavior explicit.
    exp_http = formatdate(int(expires), usegmt=True)
    return f"{AUTH_COOKIE}={token}; Max-Age={SESSION_DAYS*86400}; Expires={exp_http}; Path=/; HttpOnly; SameSite=Lax"

def clear_cookie_header():
    return f"{AUTH_COOKIE}=; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/; HttpOnly; SameSite=Lax"

def parse_cookies(header):
    out = {}
    for part in str(header or "").split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            out[k] = urllib.parse.unquote(v)
    return out

def cookie_values(header, name):
    vals = []
    for part in str(header or "").split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            if k == name:
                vals.append(urllib.parse.unquote(v))
    return vals

def client_ip_from_headers(headers, fallback=""):
    xf = str(headers.get("X-Forwarded-For", "") or "").split(",")[0].strip()
    return xf or fallback or ""

def public_user(user):
    return {
        "username": user.get("username"),
        "role": user.get("role", "viewer"),
        "locked_until": int(user.get("locked_until", 0) or 0),
        "totp_enabled": bool(user.get("totp_enabled")),
        "force_password_change": bool(user.get("force_password_change")),
        "password_changed_at": int(user.get("password_changed_at", 0) or 0),
    }

def audit_login(state, username, ok, ip, reason=""):
    entries = state.setdefault("login_audit", [])
    entries.append({
        "ts": int(time.time()),
        "ip": str(ip or "")[:80],
        "username": normalize_username(username),
        "success": bool(ok),
        "reason": str(reason or "")[:120],
    })
    state["login_audit"] = entries[-100:]

def minutes_until(ts):
    return max(1, int((int(ts or 0) - int(time.time()) + 59) // 60))

def password_expiry_state(state, user):
    settings = state.get("security_settings", {}) if isinstance(state.get("security_settings"), dict) else {}
    if not settings.get("password_expiry_enabled"):
        return {"enabled": False, "expired": False, "warning_days": None}
    days = int(settings.get("password_expiry_days") or 90)
    changed = int(user.get("password_changed_at", 0) or 0)
    if not changed:
        changed = int(time.time())
        user["password_changed_at"] = changed
    expires = changed + days * 86400
    remaining_days = int((expires - int(time.time())) // 86400)
    expired = expires <= int(time.time()) or bool(user.get("force_password_change"))
    return {"enabled": True, "expired": expired, "warning_days": remaining_days if remaining_days <= 7 else None, "expires": expires, "days": days}

def _totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

def _totp_code(secret, for_time=None, step=30, digits=6):
    if for_time is None:
        for_time = int(time.time())
    key = base64.b32decode(str(secret).upper() + "=" * ((8 - len(str(secret)) % 8) % 8))
    msg = struct.pack(">Q", int(for_time // step))
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[off:off+4])[0] & 0x7fffffff) % (10 ** digits)
    return str(code).zfill(digits)

def verify_totp(secret, code):
    code = re.sub(r"\s+", "", str(code or ""))
    if not re.fullmatch(r"\d{6}", code):
        return False
    now = int(time.time())
    return any(hmac.compare_digest(_totp_code(secret, now + offset * 30), code) for offset in (-1, 0, 1))

def otpauth_uri(username, secret):
    issuer = "MRDTech NOC"
    label = urllib.parse.quote(f"{issuer}:{username}")
    qs = urllib.parse.urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": "6", "period": "30"})
    return f"otpauth://totp/{label}?{qs}"

def qr_url_for(uri):
    # External QR rendering avoids adding fat image dependencies to a tiny container. Manual key is also shown.
    return "https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=" + urllib.parse.quote(uri)

def user_from_api_token(state, headers):
    auth = str(headers.get("Authorization", "") or "")
    if not auth.lower().startswith("bearer "):
        return None
    raw = auth.split(None, 1)[1].strip()
    if not raw:
        return None
    th = hashlib.sha256(raw.encode()).hexdigest()
    now = int(time.time())
    for tok in state.get("api_tokens", []):
        if tok.get("token_hash") == th and (not int(tok.get("expires", 0) or 0) or int(tok.get("expires", 0) or 0) > now):
            rec = find_user(state, tok.get("username"))
            if rec:
                tok["last_used"] = now
                write_state_config(state)
                pub = public_user(rec)
                pub["api_token"] = True
                return pub
    return None

def current_user_from_headers(headers, ip=""):
    tokens = [t for t in cookie_values(headers.get("Cookie"), AUTH_COOKIE) if t]
    state = read_state_config()
    if not tokens:
        return user_from_api_token(state, headers)
    token_hashes = {hashlib.sha256(t.encode()).hexdigest() for t in tokens}
    now = int(time.time())
    valid_sessions = []
    found = None
    changed = False
    for sess in state.get("sessions", []):
        if int(sess.get("expires", 0)) <= now:
            changed = True
            continue
        if sess.get("token_hash") in token_hashes:
            user = find_user(state, sess.get("username"))
            if user:
                sess["last_activity"] = now
                if ip and not sess.get("ip"):
                    sess["ip"] = ip
                changed = True
                pub = public_user(user)
                exp = password_expiry_state(state, user)
                pub.update({"password_expired": exp.get("expired"), "password_warning_days": exp.get("warning_days")})
                found = pub
        valid_sessions.append(sess)
    if changed:
        state["sessions"] = valid_sessions
        write_state_config(state)
    return found

def login_page_html(setup_required=False, error=""):
    dashboard_title = read_dashboard_config().get("dashboard_title") or DEFAULT_DASHBOARD_CONFIG["dashboard_title"]
    title = f"{dashboard_title} Login"
    title_html = html.escape(title)
    subtitle_html = "Authentication"
    error_html = html.escape(str(error or ""))
    if setup_required:
        form = """<form id='auth-form'>
          <label>Username</label><input id='username' autocomplete='username' autofocus>
          <label>Password</label><input id='password' type='password' autocomplete='new-password'>
          <label>Confirm Password</label><input id='confirm' type='password' autocomplete='new-password'>
          <div class='req'>Minimum 8 characters, at least one uppercase, one lowercase, and one number OR symbol.</div>
          <button type='submit'>Create Admin Account</button>
        </form>"""
        endpoint = "/api/setup-admin"
    else:
        form = """<form id='auth-form'>
          <label>Username</label><input id='username' autocomplete='username' autofocus>
          <label>Password</label><input id='password' type='password' autocomplete='current-password'>
          <div id='totp-wrap' style='display:none'><label>Two-factor code</label><input id='totp_code' inputmode='numeric' autocomplete='one-time-code' placeholder='123456'></div>
          <label class='remember'><input id='remember' type='checkbox' checked> Remember me</label>
          <button type='submit'>Login</button>
        </form>"""
        endpoint = "/api/login"
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title_html}</title><link rel='icon' id='noc-favicon' type='image/svg+xml' href=''>
<style>
:root{{--bg:#050805;--panel:#0f150f;--panel2:#121a12;--line:#1c2a1c;--green:#00ff41;--warn:#ffaa00;--txt:#c8e6c8;--muted:#6f8a6f;--crit:#ff3b3b}}
body{{margin:0;min-height:100vh;background:radial-gradient(circle at 50% 0%,#0d160d 0%,#050805 70%);color:var(--txt);font-family:'SF Mono',Menlo,Consolas,'Roboto Mono',monospace;display:flex;align-items:center;justify-content:center}}
.box{{width:min(440px,92vw);background:linear-gradient(180deg,var(--panel),#090d09);border:1px solid var(--line);box-shadow:0 0 40px rgba(0,255,65,.08);border-radius:8px;padding:28px}}
h1{{margin:0 0 6px;color:var(--green);letter-spacing:3px;text-transform:uppercase;font-size:18px}}
.sub{{color:var(--muted);font-size:12px;margin-bottom:24px}}
label{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:12px 0 5px}}
input{{box-sizing:border-box;width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--txt);padding:11px;border-radius:4px;font:inherit}}
input:focus{{outline:none;border-color:var(--green);box-shadow:0 0 0 1px rgba(0,255,65,.18)}}
.remember{{display:flex;gap:8px;align-items:center;text-transform:none;letter-spacing:0;color:var(--txt)}}
.remember input{{width:auto;accent-color:var(--green)}}
button{{width:100%;margin-top:18px;background:var(--green);border:1px solid var(--green);color:#000;padding:11px;border-radius:4px;font:inherit;font-weight:700;text-transform:uppercase;letter-spacing:2px;cursor:pointer}}
.err{{display:none;background:rgba(255,59,59,.1);border:1px solid rgba(255,59,59,.5);color:var(--crit);padding:9px;border-radius:4px;font-size:12px;margin-bottom:12px}}
.req{{color:var(--muted);font-size:11px;margin-top:8px;line-height:1.4}}
</style></head><body><div class='box'><h1>{title_html}</h1><div class='sub'>{subtitle_html}</div><div id='err' class='err'>{error_html}</div>{form}</div>
<script>
function updateFavicon(){{
  var color = getComputedStyle(document.documentElement).getPropertyValue('--green').trim() || '#00ff41';
  var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="' + color + '"/></svg>';
  var el = document.getElementById('noc-favicon'); if (el) el.href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}}
updateFavicon();
const endpoint={json.dumps(endpoint)};
document.getElementById('auth-form').addEventListener('submit', async e=>{{
  e.preventDefault();
  const payload={{username:username.value.trim(), password:password.value, remember:true}};
  const confirmEl = document.getElementById('confirm');
  if (confirmEl) payload.confirm_password=confirmEl.value;
  const totpEl = document.getElementById('totp_code');
  if (totpEl && totpEl.value.trim()) payload.totp_code=totpEl.value.trim();
  const err=document.getElementById('err'); err.style.display='none';
  const r=await fetch(endpoint,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
  const d=await r.json().catch(()=>({{error:'Authentication failed'}}));
  if (d.totp_required) {{ var w=document.getElementById('totp-wrap'); if(w) w.style.display='block'; err.textContent=d.error||'Two-factor code required.'; err.style.display='block'; return; }}
  if(!r.ok||!d.ok){{err.textContent=d.error||'Authentication failed';err.style.display='block';return;}}
  location.href='/';
}});
</script></body></html>"""

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
    "seerr":        ("collect_seerr",    ["SEERR_URL", "SEERR_API_KEY"]),
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
    "SEERR_URL":           {"label": "URL (http://ip:port)",    "type": "text"},
    "SEERR_API_KEY":       {"label": "API Key",                 "type": "password"},
    "OVERSEERR_URL":       {"label": "Legacy URL alias",         "type": "text"},
    "OVERSEERR_API_KEY":   {"label": "Legacy API Key alias",     "type": "password"},
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

    def send_json(self, code, obj, extra_headers=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, code, html_text, extra_headers=None):
        body = html_text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def client_ip(self):
        return client_ip_from_headers(self.headers, self.client_address[0] if self.client_address else "")

    def current_user(self):
        return current_user_from_headers(self.headers, self.client_ip())

    def is_admin(self):
        user = self.current_user()
        return bool(user and user.get("role") == "admin")

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
        path = urllib.parse.urlparse(self.path).path
        user = self.current_user()
        if path == "/login":
            if user:
                self.redirect("/")
            else:
                self.send_html(200, login_page_html(setup_required=not users_exist()))
            return
        if path == "/api/auth-status":
            self.send_json(200, {"ok": True, "authenticated": bool(user), "user": user, "setup_required": not users_exist()})
            return
        if path.startswith("/api/") and not user:
            self.send_json(401, {"error": "authentication required"})
            return
        if path == "/api/dashboard-config":
            self.send_json(200, public_dashboard_config())
            return
        if path == "/api/integration-fields":
            # Return field defs for the UI
            result = {}
            for itype, (fn_name, keys) in COLLECTOR_MAP.items():
                result[itype] = [
                    {"key": k, **FIELD_DEFS.get(k, {"label": k, "type": "text"})}
                    for k in keys
                ]
            self.send_json(200, result)
            return
        if path == "/api/custom-cards":
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
        if path == "/api/builtin-card-configs":
            # Return saved built-in card display configs
            try:
                with open(BUILTIN_CARD_CONFIGS_FILE) as f:
                    data = f.read()
            except FileNotFoundError:
                data = "{}"
            except Exception:
                data = "{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode())
            return
        if path == "/api/current-config":
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
        if path == "/" or path == "/index.html":
            if not user:
                self.redirect("/login")
                return
        super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        user = self.current_user()
        public_posts = {"/api/login", "/api/setup-admin"}
        if path not in public_posts and not user:
            self.send_json(401, {"error": "authentication required"})
            return
        if path == "/api/setup-admin":
            try:
                if users_exist():
                    self.send_json(409, {"error": "admin account already exists"})
                    return
                payload = self.read_body()
                username = normalize_username(payload.get("username"))
                password = payload.get("password", "")
                confirm = payload.get("confirm_password", "")
                if not username:
                    self.send_json(400, {"error": "Username is required."})
                    return
                if password != confirm:
                    self.send_json(400, {"error": "Passwords do not match."})
                    return
                err = password_error(password)
                if err:
                    self.send_json(400, {"error": err})
                    return
                state = read_state_config()
                now = int(time.time())
                state["users"] = [{"username": username, "password_hash": hash_password(password), "role": "admin", "password_changed_at": now, "failed_attempts": 0, "locked_until": 0}]
                token, exp = new_session(state, username, self.client_ip(), self.headers.get("User-Agent", ""))
                audit_login(state, username, True, self.client_ip(), "setup-admin")
                write_state_config(state)
                self.send_json(200, {"ok": True, "user": {"username": username, "role": "admin"}}, {"Set-Cookie": cookie_header(token, exp)})
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return
        if path == "/api/login":
            try:
                payload = self.read_body()
                state = read_state_config()
                username = normalize_username(payload.get("username"))
                user_rec = find_user(state, username)
                ip = self.client_ip()
                now = int(time.time())
                if not user_rec:
                    audit_login(state, username, False, ip, "unknown user")
                    write_state_config(state)
                    self.send_json(401, {"error": "Invalid username or password."})
                    return
                locked_until = int(user_rec.get("locked_until", 0) or 0)
                if locked_until > now:
                    audit_login(state, username, False, ip, "locked")
                    write_state_config(state)
                    self.send_json(423, {"error": f"Account locked, try again in {minutes_until(locked_until)} minutes"})
                    return
                if not verify_password(payload.get("password", ""), user_rec.get("password_hash")):
                    user_rec["failed_attempts"] = int(user_rec.get("failed_attempts", 0) or 0) + 1
                    reason = "bad password"
                    if user_rec["failed_attempts"] >= 5:
                        user_rec["locked_until"] = now + 15 * 60
                        reason = "locked after 5 failed attempts"
                    audit_login(state, username, False, ip, reason)
                    write_state_config(state)
                    if user_rec.get("locked_until", 0) > now:
                        self.send_json(423, {"error": "Account locked, try again in 15 minutes"})
                    else:
                        self.send_json(401, {"error": "Invalid username or password."})
                    return
                if user_rec.get("totp_enabled"):
                    code = payload.get("totp_code", "")
                    if not code:
                        self.send_json(401, {"error": "Two-factor code required.", "totp_required": True})
                        return
                    if not verify_totp(user_rec.get("totp_secret", ""), code):
                        audit_login(state, username, False, ip, "bad totp")
                        write_state_config(state)
                        self.send_json(401, {"error": "Invalid two-factor code.", "totp_required": True})
                        return
                user_rec["failed_attempts"] = 0
                user_rec["locked_until"] = 0
                exp_state = password_expiry_state(state, user_rec)
                if exp_state.get("expired"):
                    user_rec["force_password_change"] = True
                token, exp = new_session(state, user_rec.get("username"), ip, self.headers.get("User-Agent", ""))
                audit_login(state, username, True, ip, "success")
                write_state_config(state)
                self.send_json(200, {"ok": True, "user": {"username": user_rec.get("username"), "role": user_rec.get("role", "viewer")}, "password_expired": bool(exp_state.get("expired")), "password_warning_days": exp_state.get("warning_days")}, {"Set-Cookie": cookie_header(token, exp)})
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return
        if path == "/api/logout":
            tokens = [t for t in cookie_values(self.headers.get("Cookie"), AUTH_COOKIE) if t]
            state = read_state_config()
            if tokens:
                token_hashes = {hashlib.sha256(t.encode()).hexdigest() for t in tokens}
                state["sessions"] = [s for s in state.get("sessions", []) if s.get("token_hash") not in token_hashes]
                write_state_config(state)
            self.send_json(200, {"ok": True}, {"Set-Cookie": clear_cookie_header()})
            return
        if path == "/api/change-password":
            payload = self.read_body()
            old_password = payload.get("old_password", "")
            new_password = payload.get("new_password", "")
            confirm = payload.get("confirm_password", "")
            if new_password != confirm:
                self.send_json(400, {"error": "Passwords do not match."})
                return
            err = password_error(new_password)
            if err:
                self.send_json(400, {"error": err})
                return
            state = read_state_config()
            rec = find_user(state, user.get("username"))
            if not rec or not verify_password(old_password, rec.get("password_hash")):
                self.send_json(401, {"error": "Current password is incorrect."})
                return
            rec["password_hash"] = hash_password(new_password)
            rec["password_changed_at"] = int(time.time())
            rec["force_password_change"] = False
            write_state_config(state)
            self.send_json(200, {"ok": True})
            return
        if path == "/api/users":
            if not self.is_admin():
                self.send_json(403, {"error": "admin role required"})
                return
            state = read_state_config()
            users = []
            now = int(time.time())
            for u in state.get("users", []):
                users.append({"username": u.get("username"), "role": u.get("role", "viewer"), "locked": int(u.get("locked_until", 0) or 0) > now, "locked_until": int(u.get("locked_until", 0) or 0), "totp_enabled": bool(u.get("totp_enabled")), "force_password_change": bool(u.get("force_password_change"))})
            self.send_json(200, {"ok": True, "users": users})
            return
        if path in ("/api/users/create", "/api/users/reset-password", "/api/users/delete", "/api/users/unlock", "/api/users/reset-2fa"):
            if not self.is_admin():
                self.send_json(403, {"error": "admin role required"})
                return
            payload = self.read_body()
            state = read_state_config()
            username = normalize_username(payload.get("username"))
            if not username:
                self.send_json(400, {"error": "Username is required."})
                return
            if path == "/api/users/create":
                if find_user(state, username):
                    self.send_json(409, {"error": "User already exists."})
                    return
                role = payload.get("role", "viewer") if payload.get("role") in ("admin", "viewer") else "viewer"
                err = password_error(payload.get("password", ""))
                if err:
                    self.send_json(400, {"error": err})
                    return
                state["users"].append({"username": username, "password_hash": hash_password(payload.get("password", "")), "role": role, "password_changed_at": int(time.time()), "failed_attempts": 0, "locked_until": 0})
            elif path == "/api/users/reset-password":
                rec = find_user(state, username)
                if not rec:
                    self.send_json(404, {"error": "User not found."})
                    return
                err = password_error(payload.get("password", ""))
                if err:
                    self.send_json(400, {"error": err})
                    return
                rec["password_hash"] = hash_password(payload.get("password", ""))
                rec["password_changed_at"] = int(time.time())
                rec["force_password_change"] = False
                rec["failed_attempts"] = 0
                rec["locked_until"] = 0
            elif path == "/api/users/unlock":
                rec = find_user(state, username)
                if not rec:
                    self.send_json(404, {"error": "User not found."})
                    return
                rec["failed_attempts"] = 0
                rec["locked_until"] = 0
            elif path == "/api/users/reset-2fa":
                rec = find_user(state, username)
                if not rec:
                    self.send_json(404, {"error": "User not found."})
                    return
                rec.pop("totp_secret", None)
                rec["totp_enabled"] = False
            elif path == "/api/users/delete":
                if normalize_username(user.get("username")).lower() == username.lower():
                    self.send_json(400, {"error": "You cannot delete your own account."})
                    return
                before = len(state.get("users", []))
                state["users"] = [u for u in state.get("users", []) if normalize_username(u.get("username")).lower() != username.lower()]
                if len(state["users"]) == before:
                    self.send_json(404, {"error": "User not found."})
                    return
                state["sessions"] = [sess for sess in state.get("sessions", []) if normalize_username(sess.get("username")).lower() != username.lower()]
                state["api_tokens"] = [tok for tok in state.get("api_tokens", []) if normalize_username(tok.get("username")).lower() != username.lower()]
            write_state_config(state)
            self.send_json(200, {"ok": True})
            return
        if path in ("/api/login-history", "/api/security-settings"):
            if not self.is_admin():
                self.send_json(403, {"error": "admin role required"})
                return
            state = read_state_config()
            if path == "/api/login-history":
                self.send_json(200, {"ok": True, "entries": list(reversed(state.get("login_audit", [])[-100:]))})
            else:
                payload = self.read_body()
                settings = state.get("security_settings", {})
                if payload:
                    settings["password_expiry_enabled"] = bool(payload.get("password_expiry_enabled"))
                    days = int(payload.get("password_expiry_days") or 90)
                    settings["password_expiry_days"] = days if days in (30, 60, 90, 180) else 90
                    state["security_settings"] = settings
                    write_state_config(state)
                self.send_json(200, {"ok": True, "settings": settings})
            return
        if path == "/api/sessions":
            state = read_state_config()
            current_hashes = {hashlib.sha256(t.encode()).hexdigest() for t in cookie_values(self.headers.get("Cookie"), AUTH_COOKIE) if t}
            sessions = []
            for sess in state.get("sessions", []):
                if user.get("role") == "admin" or normalize_username(sess.get("username")).lower() == normalize_username(user.get("username")).lower():
                    sessions.append({"id": sess.get("id") or sess.get("token_hash", "")[:12], "username": sess.get("username"), "created": sess.get("created"), "last_activity": sess.get("last_activity"), "ip": sess.get("ip"), "user_agent": sess.get("user_agent"), "current": sess.get("token_hash") in current_hashes})
            self.send_json(200, {"ok": True, "sessions": sessions})
            return
        if path == "/api/sessions/revoke":
            payload = self.read_body()
            sid = str(payload.get("id", ""))
            state = read_state_config()
            kept=[]; removed=False
            for sess in state.get("sessions", []):
                match = (sess.get("id") == sid or str(sess.get("token_hash", "")).startswith(sid))
                allowed = user.get("role") == "admin" or normalize_username(sess.get("username")).lower() == normalize_username(user.get("username")).lower()
                if match and allowed:
                    removed=True
                    continue
                kept.append(sess)
            state["sessions"] = kept
            write_state_config(state)
            self.send_json(200, {"ok": removed})
            return
        if path in ("/api/2fa/setup", "/api/2fa/enable", "/api/2fa/disable"):
            state = read_state_config()
            rec = find_user(state, user.get("username"))
            if not rec:
                self.send_json(404, {"error": "User not found."})
                return
            if path == "/api/2fa/setup":
                secret = _totp_secret()
                rec["totp_pending_secret"] = secret
                write_state_config(state)
                uri = otpauth_uri(rec.get("username"), secret)
                self.send_json(200, {"ok": True, "secret": secret, "otpauth_uri": uri, "qr_url": qr_url_for(uri)})
                return
            payload = self.read_body()
            if path == "/api/2fa/enable":
                secret = rec.get("totp_pending_secret") or rec.get("totp_secret")
                if not secret or not verify_totp(secret, payload.get("code", "")):
                    self.send_json(400, {"error": "Invalid two-factor code."})
                    return
                rec["totp_secret"] = secret
                rec["totp_enabled"] = True
                rec.pop("totp_pending_secret", None)
            else:
                if not verify_password(payload.get("password", ""), rec.get("password_hash")):
                    self.send_json(401, {"error": "Current password is incorrect."})
                    return
                rec.pop("totp_secret", None)
                rec.pop("totp_pending_secret", None)
                rec["totp_enabled"] = False
            write_state_config(state)
            self.send_json(200, {"ok": True})
            return
        if path in ("/api/api-tokens", "/api/api-tokens/create", "/api/api-tokens/revoke"):
            state = read_state_config()
            now = int(time.time())
            if path == "/api/api-tokens":
                toks = []
                for tok in state.get("api_tokens", []):
                    if normalize_username(tok.get("username")).lower() == normalize_username(user.get("username")).lower():
                        toks.append({k: tok.get(k) for k in ("id", "name", "created", "expires", "last_used")})
                self.send_json(200, {"ok": True, "tokens": toks})
                return
            payload = self.read_body()
            if path == "/api/api-tokens/create":
                raw = "noc_" + secrets.token_urlsafe(32)
                days = int(payload.get("expiry_days") or 0)
                rec = {"id": uuid.uuid4().hex, "username": user.get("username"), "name": str(payload.get("name") or "API Token")[:80], "token_hash": hashlib.sha256(raw.encode()).hexdigest(), "created": now, "expires": now + days*86400 if days > 0 else 0, "last_used": 0}
                state.setdefault("api_tokens", []).append(rec)
                write_state_config(state)
                self.send_json(200, {"ok": True, "token": raw, "record": {k: rec.get(k) for k in ("id", "name", "created", "expires")}})
                return
            tid = str(payload.get("id", ""))
            before = len(state.get("api_tokens", []))
            state["api_tokens"] = [tok for tok in state.get("api_tokens", []) if not (tok.get("id") == tid and normalize_username(tok.get("username")).lower() == normalize_username(user.get("username")).lower())]
            write_state_config(state)
            self.send_json(200, {"ok": len(state.get("api_tokens", [])) < before})
            return
        if path in ("/save-layout", "/save-config", "/save-dashboard-config", "/test-connection", "/save-custom-cards", "/save-builtin-card-configs", "/regenerate") and not self.is_admin():
            if not (path == "/regenerate" and not users_exist()):
                self.send_json(403, {"error": "admin role required"})
                return
        if path == "/save-layout":
            try:
                layout = self.read_body()
                with open(LAYOUT_FILE, "w") as f:
                    json.dump(layout, f, indent=2)
                self.send_json(200, {"ok": True})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == "/regenerate":
            threading.Thread(target=_run_regen, daemon=True).start()
            self.send_json(202, {"ok": True, "msg": "regenerating"})

        elif path == "/save-config":
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

        elif path == "/save-dashboard-config":
            try:
                cfg = write_dashboard_config(self.read_body())
                print(f"Dashboard config saved: {CONFIG_FILE}")
                threading.Thread(target=_run_regen, daemon=True).start()
                self.send_json(200, {"ok": True, "config": cfg, "regen": True})
            except Exception as e2:
                self.send_json(500, {"error": str(e2)})

        elif path == "/test-connection":
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

        elif path == "/save-custom-cards":
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

        elif path == "/save-builtin-card-configs":
            # Receive object of built-in card display configs, persist to disk
            try:
                payload = self.read_body()
                if not isinstance(payload, dict):
                    self.send_json(400, {"error": "expected object"})
                    return
                import json as _json
                with open(BUILTIN_CARD_CONFIGS_FILE, "w") as f:
                    _json.dump(payload, f, indent=2)
                self.send_json(200, {"ok": True, "count": len(payload)})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == "/api/fetch-custom":
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
