#!/usr/bin/env python3
"""
NOC Dashboard — FastAPI backend server
Wraps existing collectors, serves JSON API + React frontend static files.

Endpoints:
  GET  /api/card-types            list of known card types with metadata
  GET  /api/data/{card_type}      run collector, return live data as JSON
  GET  /api/themes                all themes as CSS variable maps
  GET  /api/layout                current layout.json
  POST /api/layout                save layout.json
  GET  /api/config                dashboard.yaml top-level config (title, subtitle, etc.)
  GET  /                          React app (served from frontend/dist/)
  GET  /{path}                    static fallback to frontend/dist/

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8081
"""

import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed.", file=sys.stderr)
    sys.exit(1)

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    print("ERROR: fastapi not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

# ── Project root ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "trends.json"
THEMES_DIR = ROOT / "themes"
FRONTEND_DIST = ROOT / "frontend" / "dist"
LAYOUT_FILE = STATE_DIR / "layout.json"
CONFIG_FILE = ROOT / (os.environ.get("CONFIG_FILE") or "dashboard.yaml")
ENV_FILE = ROOT / ".env"

# ── Env loader ─────────────────────────────────────────────────────────────────

def load_env(path):
    d = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r'^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)$', line.rstrip("\n"))
                if m:
                    d[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    for k, v in os.environ.items():
        if k in d or k.isupper():
            d[k] = v
    return d


E = load_env(ENV_FILE)

# ── Theme loader ───────────────────────────────────────────────────────────────

THEME_DEFAULTS = {
    "background": "#0a0a0a",
    "card_background": "#111111",
    "card_border": "#1e1e1e",
    "accent": "#00ff41",
    "accent_secondary": "#00cc33",
    "text_primary": "#e0e0e0",
    "text_secondary": "#a0a0a0",
    "text_muted": "#555555",
    "ok_color": "#00ff41",
    "warn_color": "#ffaa00",
    "error_color": "#ff3333",
    "critical_color": "#ff0000",
    "font_family": "JetBrains Mono, Fira Code, monospace",
    "font_size_base": "13px",
    "heading_font": "JetBrains Mono, Fira Code, monospace",
    "card_border_radius": "4px",
    "card_shadow": "0 0 8px rgba(0,255,65,0.08)",
    "section_header_color": "#00ff41",
    "graph_line_color": "#00ff41",
    "graph_fill_color": "rgba(0,255,65,0.12)",
    "gauge_track_color": "#1a1a1a",
    "gauge_fill_ok": "#00ff41",
    "gauge_fill_warn": "#ffaa00",
    "gauge_fill_critical": "#ff3333",
    "sparkline_stroke_width": "2",
    "top_bar_background": "#000000",
    "top_bar_border": "#1a1a1a",
}


def load_all_themes():
    themes = {}
    for f in THEMES_DIR.glob("*.yaml"):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh) or {}
            merged = dict(THEME_DEFAULTS)
            merged.update({k: v for k, v in data.items() if k not in ("name", "description")})
            themes[f.stem] = merged
        except Exception:
            pass
    # Always have dark-noc as fallback
    if not themes:
        themes["dark-noc"] = dict(THEME_DEFAULTS)
    return themes


# ── Dashboard config ───────────────────────────────────────────────────────────

def load_dashboard_config():
    try:
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ── Collector dispatch ─────────────────────────────────────────────────────────

def get_collector_map():
    from collectors import (
        proxmox, wazuh, malware_sources, docker_portainer, pbs, uptime_kuma,
        crowdsec, unifi, adguard, home_assistant, smart_health, urbackup,
        qnap, media, cloudflare, nginx_proxy, tailscale, limacharlie, custom_url
    )
    return {
        "proxmox": proxmox.collect,
        "proxmox_storage": proxmox.collect_storage,
        "wazuh": wazuh.collect,
        "malware_sources": malware_sources.collect,
        "docker": docker_portainer.collect,
        "pbs": pbs.collect,
        "uptime_kuma": uptime_kuma.collect,
        "crowdsec": crowdsec.collect,
        "unifi": unifi.collect,
        "adguard": adguard.collect,
        "home_assistant": home_assistant.collect,
        "smart_health": smart_health.collect,
        "urbackup": urbackup.collect,
        "qnap": qnap.collect,
        "plex": media.collect_plex,
        "tautulli": media.collect_tautulli,
        "sonarr": media.collect_sonarr,
        "radarr": media.collect_radarr,
        "prowlarr": media.collect_prowlarr,
        "sabnzbd": media.collect_sabnzbd,
        "overseerr": media.collect_overseerr,
        "cloudflare": cloudflare.collect,
        "nginx_proxy": nginx_proxy.collect,
        "tailscale": tailscale.collect,
        "limacharlie": limacharlie.collect,
        "custom_url": custom_url.collect,
        "wan_health": unifi.collect,
    }


CARD_TYPE_META = {
    "proxmox": {"label": "Proxmox", "description": "Proxmox node CPU, RAM, VMs, storage"},
    "proxmox_storage": {"label": "Proxmox Storage", "description": "Proxmox storage pool usage donuts"},
    "docker": {"label": "Docker", "description": "Container counts and unhealthy containers"},
    "pbs": {"label": "Proxmox Backup Server", "description": "Backup tasks, last backup time, datastore usage"},
    "urbackup": {"label": "URBackup", "description": "Client backup status"},
    "uptime_kuma": {"label": "Uptime Kuma", "description": "Monitor status, cert expiry"},
    "home_assistant": {"label": "Home Assistant", "description": "Entity counts, alerts, notifications"},
    "smart_health": {"label": "Disk Health", "description": "SMART disk health from Proxmox"},
    "wazuh": {"label": "Wazuh SIEM", "description": "Agent status, alerts 24h"},
    "malware_sources": {"label": "Malware Detect", "description": "Malware feed detections"},
    "crowdsec": {"label": "CrowdSec", "description": "Bans and detections"},
    "cloudflare": {"label": "Cloudflare", "description": "Requests, threats, WAF events"},
    "unifi": {"label": "UniFi", "description": "WAN status, clients, IPS alerts"},
    "tailscale": {"label": "Tailscale", "description": "VPN device status"},
    "nginx_proxy": {"label": "Nginx Proxy Manager", "description": "Proxy hosts and cert expiry"},
    "adguard": {"label": "AdGuard Home", "description": "DNS query and block stats"},
    "qnap": {"label": "NAS Storage", "description": "QNAP NAS volumes, disks, temps"},
    "plex": {"label": "Plex", "description": "Active streams, library counts"},
    "tautulli": {"label": "Tautulli", "description": "Plex streams, plays today, top user"},
    "sonarr": {"label": "Sonarr", "description": "TV series, queue, missing"},
    "radarr": {"label": "Radarr", "description": "Movies, queue, missing"},
    "prowlarr": {"label": "Prowlarr", "description": "Indexer health"},
    "sabnzbd": {"label": "SABnzbd", "description": "Download queue and speed"},
    "overseerr": {"label": "Overseerr", "description": "Media requests"},
    "limacharlie": {"label": "LimaCharlie", "description": "Endpoint sensor status"},
    "custom_url": {"label": "Custom URL", "description": "Fetch and display custom JSON endpoint"},
    "wan_health": {"label": "WAN Health", "description": "WAN/internet status via UniFi"},
}

# ── Trend history ──────────────────────────────────────────────────────────────

def load_trends():
    STATE_DIR.mkdir(exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_trends(trends):
    STATE_DIR.mkdir(exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(trends, f)


def update_trends_for(card_type, data, now_epoch, trends):
    """Append current value to trend series for cards that support graphs."""
    MAX_HOURS = 48
    cutoff = now_epoch - MAX_HOURS * 3600
    TREND_FIELDS = {
        "proxmox": ["cpu"],
        "adguard": ["block_pct", "queries"],
        "wazuh": ["alerts_24h", "high_24h"],
    }
    fields = TREND_FIELDS.get(card_type, [])
    for field in fields:
        val = data.get(field)
        if val is None:
            continue
        series_key = f"{card_type}.{field}"
        series = trends.get(series_key, [])
        series.append([now_epoch, float(val)])
        series = [[t, v] for t, v in series if t >= cutoff]
        trends[series_key] = series
    return trends


# ── Layout persistence ─────────────────────────────────────────────────────────

DEFAULT_LAYOUT = {
    "theme": "dark-noc",
    "autoTheme": True,
    "dayTheme": "light-clean",
    "nightTheme": "dark-noc",
    "dayStart": 7,
    "nightStart": 19,
    "cards": []
}


def load_layout():
    STATE_DIR.mkdir(exist_ok=True)
    if LAYOUT_FILE.exists():
        try:
            with open(LAYOUT_FILE) as f:
                data = json.load(f)
            # Ensure required keys exist
            for k, v in DEFAULT_LAYOUT.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    # Bootstrap from dashboard.yaml
    return _bootstrap_layout_from_yaml()


def _bootstrap_layout_from_yaml():
    """Generate an initial layout.json from dashboard.yaml sections/cards."""
    cfg = load_dashboard_config()
    theme_cfg = cfg.get("theme", {})
    layout = {
        "theme": theme_cfg.get("preset", "dark-noc"),
        "autoTheme": theme_cfg.get("auto_switch", True),
        "dayTheme": theme_cfg.get("day_theme", "light-clean"),
        "nightTheme": theme_cfg.get("night_theme", "dark-noc"),
        "dayStart": int(theme_cfg.get("day_start", "07:00").split(":")[0]),
        "nightStart": int(theme_cfg.get("night_start", "19:00").split(":")[0]),
        "cards": []
    }
    import uuid
    SIZE_TO_WH = {
        "normal": (1, 2),
        "wide": (2, 2),
        "tall": (1, 4),
        "large": (2, 4),
    }
    x, y, col = 0, 0, 0
    COLS = 4
    for section in cfg.get("sections", []):
        for card in section.get("cards", []):
            size = card.get("size", "normal")
            w, h = SIZE_TO_WH.get(size, (1, 2))
            if x + w > COLS:
                x = 0
                y += 2
            entry = {
                "id": str(uuid.uuid4()),
                "type": card.get("type", ""),
                "title": card.get("title", card.get("type", "").upper()),
                "x": x, "y": y, "w": w, "h": h,
                "config": {
                    "graph": card.get("graph", False),
                    "graph_type": card.get("graph_type", "sparkline"),
                    "graph_field": card.get("graph_field", ""),
                    "graph_color": card.get("graph_color", ""),
                    "thresholds": card.get("thresholds", {}),
                    "refresh_seconds": cfg.get("refresh_seconds", 60),
                }
            }
            layout["cards"].append(entry)
            x += w
            if x >= COLS:
                x = 0
                y += 2
    return layout


def save_layout(layout):
    STATE_DIR.mkdir(exist_ok=True)
    with open(LAYOUT_FILE, "w") as f:
        json.dump(layout, f, indent=2)


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(title="NOC Dashboard API", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-loaded collector map (avoids import cost at startup for health checks)
_collector_map = None


def get_collectors():
    global _collector_map
    if _collector_map is None:
        try:
            _collector_map = get_collector_map()
        except Exception as e:
            print(f"WARNING: collector import error: {e}", file=sys.stderr)
            _collector_map = {}
    return _collector_map


# ── API routes ─────────────────────────────────────────────────────────────────

@app.get("/api/card-types")
def api_card_types():
    return {k: v for k, v in CARD_TYPE_META.items()}


@app.get("/api/themes")
def api_themes():
    return load_all_themes()


@app.get("/api/layout")
def api_get_layout():
    return load_layout()


@app.post("/api/layout")
async def api_save_layout(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    save_layout(body)
    return {"ok": True}


@app.get("/api/config")
def api_config():
    cfg = load_dashboard_config()
    top_bar = cfg.get("top_bar", {})
    return {
        "title": top_bar.get("title", "NOC Dashboard"),
        "subtitle": top_bar.get("subtitle", ""),
        "show_updated": top_bar.get("show_updated", True),
        "show_overall_status": top_bar.get("show_overall_status", True),
        "overall_status_logic": top_bar.get("overall_status_logic", "worst"),
    }


@app.get("/api/data/{card_type}")
def api_data(card_type: str, request: Request):
    """Run collector and return live data. Cached for TTL seconds."""
    collectors = get_collectors()
    fn = collectors.get(card_type)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"no collector for '{card_type}'")

    # Build card_cfg from query params (graph_field, thresholds JSON, etc.)
    card_cfg = {"type": card_type}
    qp = dict(request.query_params)
    if "thresholds" in qp:
        try:
            card_cfg["thresholds"] = json.loads(qp["thresholds"])
        except Exception:
            pass
    for k in ("graph_field", "graph_type", "graph_color"):
        if k in qp:
            card_cfg[k] = qp[k]

    now = time.time()
    try:
        t0 = time.time()
        data = fn(E, card_cfg)
        elapsed = round(time.time() - t0, 3)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{card_type}] ERROR: {e}\n{tb}", file=sys.stderr)
        data = {"state": "error", "note": str(e)[:200]}
        elapsed = 0

    # Update trends (fire and forget — non-blocking write)
    try:
        trends = load_trends()
        if data.get("state") not in ("error",):
            trends = update_trends_for(card_type, data, int(now), trends)
            save_trends(trends)
    except Exception:
        pass

    # Include trend data in response so frontend can render sparklines
    try:
        trend_data = {}
        trends = load_trends()
        for k, v in trends.items():
            if k.startswith(card_type + "."):
                trend_data[k.split(".", 1)[1]] = [val for _, val in v[-60:]]
        if trend_data:
            data["_trends"] = trend_data
    except Exception:
        pass

    data["_elapsed"] = elapsed
    data["_ts"] = int(now)
    return data


@app.get("/api/health")
def api_health():
    return {"ok": True, "ts": int(time.time())}


# ── Static file serving (React app) ───────────────────────────────────────────

if FRONTEND_DIST.exists():
    # Mount static assets (js, css, etc.)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str):
        # For SPA routing — anything not matching /api/* returns index.html
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = FRONTEND_DIST / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
else:
    @app.get("/")
    def serve_no_frontend():
        return JSONResponse({"error": "Frontend not built. Run: cd frontend && npm run build"}, status_code=503)


# ── Dev entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
