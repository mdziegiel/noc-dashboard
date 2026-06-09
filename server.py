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
  GET  /api/config                dashboard.yaml top-level config
  GET  /api/ticker                aggregated alerts/stats for scrolling ticker
  GET  /api/status-overview       counts of ok/warn/crit across all cards
  GET  /api/events                SSE stream for live card updates
  GET  /                          React app (served from frontend/dist/)

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8081
"""

import asyncio
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
    from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
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
    "font_family": "JetBrains Mono, Fira Code, Consolas, monospace",
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
    "proxmox":          {"label": "Proxmox",              "description": "Proxmox node CPU, RAM, VMs, storage",      "category": "Infrastructure", "icon": "Server"},
    "proxmox_storage":  {"label": "Proxmox Storage",      "description": "Proxmox storage pool usage donuts",         "category": "Infrastructure", "icon": "HardDrive"},
    "docker":           {"label": "Docker",               "description": "Container counts and unhealthy containers", "category": "Infrastructure", "icon": "Box"},
    "pbs":              {"label": "Proxmox Backup Server","description": "Backup tasks, last backup time, datastore", "category": "Infrastructure", "icon": "Archive"},
    "urbackup":         {"label": "URBackup",             "description": "Client backup status",                      "category": "Infrastructure", "icon": "RotateCcw"},
    "home_assistant":   {"label": "Home Assistant",       "description": "Entity counts, alerts, notifications",      "category": "Infrastructure", "icon": "Home"},
    "smart_health":     {"label": "Disk Health",          "description": "SMART disk health from Proxmox",            "category": "Infrastructure", "icon": "Activity"},
    "wazuh":            {"label": "Wazuh SIEM",           "description": "Agent status, alerts 24h",                  "category": "Security",       "icon": "Shield"},
    "malware_sources":  {"label": "Malware Detect",       "description": "Malware feed detections",                   "category": "Security",       "icon": "AlertTriangle"},
    "crowdsec":         {"label": "CrowdSec",             "description": "Bans and detections",                       "category": "Security",       "icon": "ShieldAlert"},
    "cloudflare":       {"label": "Cloudflare",           "description": "Requests, threats, WAF events",             "category": "Security",       "icon": "Cloud"},
    "limacharlie":      {"label": "LimaCharlie",          "description": "Endpoint sensor status",                    "category": "Security",       "icon": "Eye"},
    "unifi":            {"label": "UniFi",                "description": "WAN status, clients, IPS alerts",           "category": "Network",        "icon": "Wifi"},
    "wan_health":       {"label": "WAN Health",           "description": "WAN/internet status via UniFi",             "category": "Network",        "icon": "Wifi"},
    "tailscale":        {"label": "Tailscale",            "description": "VPN device status",                         "category": "Network",        "icon": "Network"},
    "nginx_proxy":      {"label": "Nginx Proxy Manager",  "description": "Proxy hosts and cert expiry",               "category": "Network",        "icon": "Globe"},
    "adguard":          {"label": "AdGuard Home",         "description": "DNS query and block stats",                 "category": "Network",        "icon": "Filter"},
    "qnap":             {"label": "NAS Storage",          "description": "QNAP NAS volumes, disks, temps",            "category": "Storage",        "icon": "Database"},
    "plex":             {"label": "Plex",                 "description": "Active streams, library counts",            "category": "Media",          "icon": "Play"},
    "tautulli":         {"label": "Tautulli",             "description": "Plex streams, plays today, top user",       "category": "Media",          "icon": "BarChart2"},
    "sonarr":           {"label": "Sonarr",               "description": "TV series, queue, missing",                 "category": "Media",          "icon": "Tv"},
    "radarr":           {"label": "Radarr",               "description": "Movies, queue, missing",                    "category": "Media",          "icon": "Film"},
    "prowlarr":         {"label": "Prowlarr",             "description": "Indexer health",                            "category": "Media",          "icon": "Search"},
    "sabnzbd":          {"label": "SABnzbd",              "description": "Download queue and speed",                  "category": "Media",          "icon": "Download"},
    "overseerr":        {"label": "Overseerr",            "description": "Media requests",                            "category": "Media",          "icon": "List"},
    "uptime_kuma":      {"label": "Uptime Kuma",          "description": "Monitor status, cert expiry",               "category": "Monitoring",     "icon": "HeartPulse"},
    "custom_url":       {"label": "Custom URL",           "description": "Fetch and display custom JSON endpoint",    "category": "Monitoring",     "icon": "ExternalLink"},
}

CATEGORY_ORDER = ["Infrastructure", "Security", "Network", "Storage", "Media", "Monitoring"]

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
    "autoTheme": False,
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
            for k, v in DEFAULT_LAYOUT.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
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


# ── Card data cache (for ticker + status overview) ─────────────────────────────

_card_cache: dict = {}  # card_type -> {"data": {...}, "ts": float}
_sse_clients: set = set()  # set of asyncio.Queue


async def _sse_broadcast(msg: str):
    """Push a message to all connected SSE clients."""
    dead = set()
    for q in list(_sse_clients):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.add(q)
    _sse_clients.difference_update(dead)


def _push_sse_from_sync(card_type: str, data: dict):
    """Schedule SSE broadcast from a sync context (runs in uvicorn's event loop)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            msg = json.dumps({"type": "card_update", "card_type": card_type, "data": data})
            asyncio.run_coroutine_threadsafe(_sse_broadcast(msg), loop)
    except Exception:
        pass


# ── Ticker extraction ──────────────────────────────────────────────────────────

def _extract_ticker_items(cache: dict) -> tuple:
    """Extract alert/stats items from card cache. Returns (items_list, worst_level)."""
    items = []
    worst = "ok"
    level_val = {"ok": 0, "info": 0, "warn": 1, "crit": 2}

    def add(text, level):
        nonlocal worst
        items.append({"text": text, "level": level})
        if level_val.get(level, 0) > level_val.get(worst, 0):
            worst = level

    now = time.time()
    STALE = 900  # 15 min

    for card_type, entry in cache.items():
        data = entry.get("data", {})
        ts = entry.get("ts", 0)
        if now - ts > STALE:
            continue
        state = data.get("state", "ok")

        if card_type == "proxmox":
            vms_off = data.get("vms_offline", 0)
            if vms_off:
                add(f"Proxmox: {vms_off} VM(s) offline", "crit")
            cpu = data.get("cpu")
            if cpu is not None:
                if cpu > 90:
                    add(f"Proxmox CPU critical: {cpu:.0f}%", "crit")
                elif cpu > 75:
                    add(f"Proxmox CPU high: {cpu:.0f}%", "warn")

        elif card_type == "proxmox_storage":
            for pool in (data.get("pools") or []):
                pct = pool.get("pct", 0)
                name = pool.get("name", "storage")
                if pct > 90:
                    add(f"Storage {name} at {pct:.0f}%", "crit")
                elif pct > 80:
                    add(f"Storage {name} at {pct:.0f}%", "warn")

        elif card_type == "docker":
            for c in (data.get("unhealthy") or [])[:3]:
                add(f"Docker unhealthy: {c}", "crit")
            for c in (data.get("stopped") or [])[:3]:
                add(f"Docker stopped: {c}", "warn")

        elif card_type == "wazuh":
            high = data.get("high_24h", 0)
            alerts = data.get("alerts_24h", 0)
            if high > 0:
                add(f"Wazuh: {high} high-severity alert(s) in 24h", "crit")
            elif alerts > 100:
                add(f"Wazuh: {alerts} alerts in 24h", "warn")
            for a in (data.get("agents") or []):
                if a.get("status") not in ("active", "Active"):
                    add(f"Wazuh agent offline: {a.get('name', a.get('id', '?'))}", "warn")

        elif card_type == "crowdsec":
            bans = data.get("active_bans", 0) or data.get("bans", 0)
            if bans > 200:
                add(f"CrowdSec: {bans} active bans", "warn")
            d24 = data.get("decisions_24h", 0) or data.get("detections_24h", 0)
            if d24 > 1000:
                add(f"CrowdSec: {d24} detections in 24h", "warn")

        elif card_type == "uptime_kuma":
            for m in (data.get("down") or [])[:4]:
                add(f"Down: {m}", "crit")
            for m in (data.get("degraded") or [])[:2]:
                add(f"Degraded: {m}", "warn")

        elif card_type == "pbs":
            failed = data.get("failed_tasks", 0)
            if failed:
                add(f"PBS: {failed} failed backup task(s) in 24h", "crit")

        elif card_type == "urbackup":
            for c in (data.get("clients_with_issues") or [])[:3]:
                name = c if isinstance(c, str) else c.get("name", str(c))
                add(f"URBackup: {name} has issues", "warn")
            for c in (data.get("overdue") or [])[:2]:
                name = c if isinstance(c, str) else c.get("name", str(c))
                add(f"URBackup: {name} backup overdue", "warn")

        elif card_type in ("unifi", "wan_health"):
            wan_st = data.get("wan_status") or data.get("wan_state")
            if wan_st and wan_st.lower() in ("down", "error", "offline"):
                add("WAN: Internet connection DOWN", "crit")
            ips = data.get("ips_alerts_24h", 0) or data.get("ips_events", 0)
            if ips > 20:
                add(f"UniFi IPS: {ips} alerts in 24h", "warn")

        elif card_type == "cloudflare":
            threats = data.get("threats_24h", 0) or data.get("threats", 0)
            if threats > 2000:
                add(f"Cloudflare: {threats} threats blocked in 24h", "warn")

        elif card_type == "nginx_proxy":
            for c in (data.get("expired_certs") or data.get("cert_invalid") or [])[:3]:
                add(f"Cert INVALID: {c}", "crit")
            for c in (data.get("expiring_soon") or [])[:2]:
                add(f"Cert expiring soon: {c}", "warn")

        elif card_type == "smart_health":
            for d in (data.get("failed") or []):
                add(f"SMART FAIL: {d}", "crit")
            for d in (data.get("warning") or [])[:2]:
                add(f"SMART warn: {d}", "warn")

        elif card_type == "malware_sources":
            det = data.get("total_detections", 0) or data.get("detections", 0)
            if det > 0:
                add(f"Malware feed: {det} detection(s)", "warn")

        elif card_type == "qnap":
            for nas in (data.get("nas") or [data] if data.get("volume_pct") else []):
                pct = nas.get("volume_pct", 0)
                n = nas.get("name", "NAS")
                if pct > 90:
                    add(f"{n}: volume at {pct:.0f}%", "crit")
                elif pct > 80:
                    add(f"{n}: volume at {pct:.0f}%", "warn")

        elif card_type == "limacharlie":
            det = data.get("detections_24h", 0)
            if det > 30:
                add(f"LimaCharlie: {det} detection(s) in 24h", "warn")

        elif card_type == "home_assistant":
            alerts = data.get("alerts", 0) or data.get("persistent_notifications", 0)
            if alerts > 5:
                add(f"Home Assistant: {alerts} active alert(s)", "warn")

        elif state in ("crit", "critical", "error"):
            label = CARD_TYPE_META.get(card_type, {}).get("label", card_type)
            add(f"{label}: {state.upper()}", "crit")
        elif state == "warn":
            label = CARD_TYPE_META.get(card_type, {}).get("label", card_type)
            add(f"{label}: WARNING", "warn")

    # Positive stats when all clear
    if not items:
        total = len(cache)
        if total > 0:
            add(f"All {total} monitored service(s) nominal", "ok")
        prox = cache.get("proxmox", {}).get("data", {})
        if prox.get("cpu") is not None:
            add(f"Proxmox: CPU {prox['cpu']:.0f}% · RAM {prox.get('mem_pct', 0):.0f}%", "ok")
        ag = cache.get("adguard", {}).get("data", {})
        if ag.get("block_pct"):
            add(f"AdGuard: blocking {ag['block_pct']:.1f}% of queries", "ok")
        uk = cache.get("uptime_kuma", {}).get("data", {})
        if uk.get("up_count"):
            add(f"Uptime Kuma: {uk['up_count']} monitors UP", "ok")
        if not items:
            add("NOC Dashboard — MRDTech // ANTON — All Systems Nominal", "ok")

    return items, worst


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(title="NOC Dashboard API", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """Run collector and return live data."""
    collectors = get_collectors()
    fn = collectors.get(card_type)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"no collector for '{card_type}'")

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

    # Cache for ticker + status overview
    _card_cache[card_type] = {"data": data, "ts": now}

    # Update trends
    try:
        trends = load_trends()
        if data.get("state") not in ("error",):
            trends = update_trends_for(card_type, data, int(now), trends)
            save_trends(trends)
    except Exception:
        pass

    # Include trend data in response
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

    # Push to SSE clients (non-blocking)
    _push_sse_from_sync(card_type, data)

    # Record alert events to persistent history
    try:
        _record_alert_events(card_type, data)
    except Exception:
        pass

    return data


@app.get("/api/ticker")
def api_ticker():
    """Aggregated alerts and stats for the scrolling ticker bar."""
    items, worst = _extract_ticker_items(_card_cache)
    return {"items": items, "worst": worst, "ts": int(time.time())}


@app.get("/api/status-overview")
def api_status_overview():
    """Counts of ok/warn/crit across all recently-seen cards."""
    now = time.time()
    STALE = 900
    counts = {"ok": 0, "warn": 0, "crit": 0, "error": 0, "unknown": 0}
    for card_type, entry in _card_cache.items():
        if now - entry.get("ts", 0) > STALE:
            continue
        state = entry.get("data", {}).get("state", "unknown")
        if state in ("crit", "critical"):
            counts["crit"] += 1
        elif state == "warn":
            counts["warn"] += 1
        elif state == "ok":
            counts["ok"] += 1
        elif state == "error":
            counts["error"] += 1
        else:
            counts["unknown"] += 1
    worst = "ok"
    if counts["crit"] + counts["error"] > 0:
        worst = "crit"
    elif counts["warn"] > 0:
        worst = "warn"
    return {**counts, "worst": worst, "total": sum(counts.values()), "ts": int(time.time())}


@app.get("/api/events")
async def api_sse():
    """Server-Sent Events stream for live card data updates."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _sse_clients.add(q)

    async def stream():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'ts': int(time.time())})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'ts': int(time.time())})}\n\n"
        except Exception:
            pass
        finally:
            _sse_clients.discard(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/health")
def api_health():
    return {"ok": True, "ts": int(time.time())}



# ── Alert history persistence ──────────────────────────────────────────────────

ALERT_HISTORY_FILE = STATE_DIR / "alert_history.json"
MAX_ALERT_HISTORY = 500  # keep last 500 events


def load_alert_history() -> list:
    STATE_DIR.mkdir(exist_ok=True)
    if ALERT_HISTORY_FILE.exists():
        try:
            with open(ALERT_HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_alert_history(events: list):
    STATE_DIR.mkdir(exist_ok=True)
    with open(ALERT_HISTORY_FILE, "w") as f:
        json.dump(events, f)


def _extract_alert_events(card_type: str, data: dict) -> list:
    """Extract named alert events from a card data payload.
    Returns list of {text, level} dicts.
    """
    events = []
    label = CARD_TYPE_META.get(card_type, {}).get("label", card_type)
    state = data.get("state", "ok")

    if card_type == "proxmox":
        vms_off = data.get("vms_offline", 0)
        if vms_off:
            events.append({"text": f"{label}: {vms_off} VM(s) offline", "level": "crit"})
        for vm in (data.get("down_vms") or []):
            events.append({"text": f"{label}: VM offline — {vm}", "level": "crit"})
        cpu = data.get("cpu_pct") or data.get("cpu")
        if cpu is not None:
            if cpu > 90:
                events.append({"text": f"{label}: CPU critical {cpu:.0f}%", "level": "crit"})
            elif cpu > 75:
                events.append({"text": f"{label}: CPU high {cpu:.0f}%", "level": "warn"})

    elif card_type == "proxmox_storage":
        for pool in (data.get("pools") or []):
            pct = pool.get("pct", 0)
            name = pool.get("name", "storage")
            if pct > 90:
                events.append({"text": f"{label}: {name} at {pct:.0f}%", "level": "crit"})
            elif pct > 80:
                events.append({"text": f"{label}: {name} at {pct:.0f}%", "level": "warn"})
        for sname, sdata in (data.get("storage") or {}).items():
            pct = sdata.get("used_pct") or sdata.get("pct") or 0
            if pct > 90:
                events.append({"text": f"{label}: {sname} at {pct:.0f}%", "level": "crit"})
            elif pct > 80:
                events.append({"text": f"{label}: {sname} at {pct:.0f}%", "level": "warn"})

    elif card_type == "docker":
        for c in (data.get("bad_containers") or data.get("unhealthy") or [])[:10]:
            name = c if isinstance(c, str) else c.get("name", str(c))
            st = (f" ({c.get('state', c.get('status', '?'))})" if isinstance(c, dict) else "")
            events.append({"text": f"Docker: {name}{st} unhealthy", "level": "crit"})
        for c in (data.get("stopped") or [])[:5]:
            name = c if isinstance(c, str) else c.get("name", str(c))
            events.append({"text": f"Docker: {name} stopped", "level": "warn"})

    elif card_type == "wazuh":
        high = data.get("high_alerts") or data.get("high_24h", 0)
        alerts = data.get("alerts_24h", 0)
        if high > 0:
            events.append({"text": f"Wazuh: {high} high-severity alert(s) in 24h", "level": "crit"})
        elif alerts > 100:
            events.append({"text": f"Wazuh: {alerts} total alerts in 24h", "level": "warn"})
        for a in (data.get("down_agents") or data.get("agents") or []):
            if isinstance(a, dict):
                status = a.get("status", "")
                if status and status.lower() not in ("active",):
                    name = a.get("name", a.get("id", str(a)))
                    events.append({"text": f"Wazuh: agent offline — {name}", "level": "warn"})

    elif card_type == "crowdsec":
        bans = data.get("active_bans", 0) or data.get("bans", 0)
        if bans > 200:
            events.append({"text": f"CrowdSec: {bans} active bans", "level": "warn"})
        d24 = data.get("decisions_24h", 0) or data.get("detections_24h", 0)
        if d24 > 1000:
            events.append({"text": f"CrowdSec: {d24} detections in 24h", "level": "warn"})

    elif card_type == "uptime_kuma":
        for m in (data.get("down") or [])[:10]:
            name = m if isinstance(m, str) else m.get("name", str(m))
            events.append({"text": f"Down: {name}", "level": "crit"})
        for m in (data.get("degraded") or [])[:5]:
            name = m if isinstance(m, str) else m.get("name", str(m))
            events.append({"text": f"Degraded: {name}", "level": "warn"})

    elif card_type == "pbs":
        failed = data.get("failed_tasks", 0)
        if failed:
            events.append({"text": f"PBS: {failed} failed backup task(s) in 24h", "level": "crit"})

    elif card_type == "urbackup":
        for c in (data.get("clients_with_issues") or [])[:5]:
            name = c if isinstance(c, str) else c.get("name", str(c))
            events.append({"text": f"URBackup: {name} has issues", "level": "warn"})
        for c in (data.get("overdue") or [])[:3]:
            name = c if isinstance(c, str) else c.get("name", str(c))
            events.append({"text": f"URBackup: {name} backup overdue", "level": "warn"})

    elif card_type in ("unifi", "wan_health"):
        wan_st = data.get("wan_status") or data.get("wan_state", "")
        if wan_st and wan_st.lower() in ("down", "error", "offline"):
            events.append({"text": "WAN: Internet connection DOWN", "level": "crit"})
        ips = data.get("ips_alerts_24h", 0) or data.get("ips_events", 0)
        if ips > 20:
            events.append({"text": f"UniFi IPS: {ips} alerts in 24h", "level": "warn"})

    elif card_type == "cloudflare":
        threats = data.get("threats_24h", 0) or data.get("threats", 0)
        if threats > 2000:
            events.append({"text": f"Cloudflare: {threats} threats blocked in 24h", "level": "warn"})

    elif card_type == "nginx_proxy":
        for c in (data.get("expired_certs") or data.get("cert_invalid") or [])[:5]:
            events.append({"text": f"Cert INVALID: {c}", "level": "crit"})
        for c in (data.get("expiring_soon") or [])[:3]:
            events.append({"text": f"Cert expiring soon: {c}", "level": "warn"})

    elif card_type == "smart_health":
        for d in (data.get("failed") or []):
            events.append({"text": f"SMART FAIL: {d}", "level": "crit"})
        for d in (data.get("warning") or [])[:3]:
            events.append({"text": f"SMART warning: {d}", "level": "warn"})

    elif card_type == "malware_sources":
        det = data.get("total_detections", 0) or data.get("detections", 0)
        if det > 0:
            events.append({"text": f"Malware feed: {det} detection(s)", "level": "warn"})

    elif card_type == "qnap":
        for nas in (data.get("nas") or ([data] if data.get("volume_pct") else [])):
            pct = nas.get("volume_pct", 0)
            n = nas.get("name", "NAS")
            if pct > 90:
                events.append({"text": f"{n}: volume at {pct:.0f}%", "level": "crit"})
            elif pct > 80:
                events.append({"text": f"{n}: volume at {pct:.0f}%", "level": "warn"})
            for disk in (nas.get("disks") or []):
                st = disk.get("health") or disk.get("status", "")
                if st and st.lower() not in ("good", "ok", "normal"):
                    events.append({"text": f"{n}: disk {disk.get('id','?')} — {st}", "level": "warn"})

    elif card_type == "limacharlie":
        det = data.get("detections_24h", 0)
        if det > 30:
            events.append({"text": f"LimaCharlie: {det} detection(s) in 24h", "level": "warn"})
        for s in (data.get("offline_sensors") or [])[:3]:
            events.append({"text": f"LimaCharlie: sensor offline — {s}", "level": "warn"})

    elif card_type == "home_assistant":
        for n in (data.get("notifications") or [])[:5]:
            text = n if isinstance(n, str) else n.get("message", n.get("title", str(n)))
            events.append({"text": f"HA: {text}", "level": "warn"})
        for e in (data.get("entity_unavailable") or [])[:3]:
            events.append({"text": f"HA: entity unavailable — {e}", "level": "warn"})

    elif card_type == "tailscale":
        for d in (data.get("offline_devices") or [])[:5]:
            name = d if isinstance(d, str) else d.get("name", d.get("hostname", str(d)))
            events.append({"text": f"Tailscale: {name} offline", "level": "warn"})

    # Fallback for unhandled card types in error/crit state
    if not events and state in ("crit", "critical", "error"):
        note = data.get("note", "")
        events.append({"text": f"{label}: {state.upper()}{' — ' + note if note else ''}", "level": "crit"})
    elif not events and state == "warn":
        events.append({"text": f"{label}: WARNING", "level": "warn"})

    return events


@app.get("/api/alert-history")
def api_get_alert_history():
    """Return persisted alert event history."""
    return {"events": load_alert_history(), "ts": int(time.time())}


@app.post("/api/alert-history/clear")
async def api_clear_alert_history():
    """Clear the alert history file."""
    save_alert_history([])
    return {"ok": True}


def _record_alert_events(card_type: str, data: dict):
    """Extract and append new alert events to persistent history.
    Deduplicates within the same minute to prevent log spam on fast refresh.
    """
    events = _extract_alert_events(card_type, data)
    if not events:
        return
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    history = load_alert_history()
    existing_texts_this_minute = {
        e["text"] for e in history
        if e.get("ts", "")[:16] == now_iso[:16]
    }
    new_entries = []
    for ev in events:
        if ev["text"] not in existing_texts_this_minute:
            new_entries.append({
                "text": ev["text"],
                "level": ev["level"],
                "card_type": card_type,
                "ts": now_iso,
            })
            existing_texts_this_minute.add(ev["text"])

    if not new_entries:
        return
    merged = new_entries + history
    merged = merged[:MAX_ALERT_HISTORY]
    save_alert_history(merged)

    # Broadcast new events to all open SSE clients
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            msg = json.dumps({"type": "alert_history_update", "new_events": new_entries})
            asyncio.run_coroutine_threadsafe(_sse_broadcast(msg), loop)
    except Exception:
        pass


# ── Static file serving (React app) ───────────────────────────────────────────

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = FRONTEND_DIST / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
else:
    @app.get("/")
    def serve_no_frontend():
        return JSONResponse(
            {"error": "Frontend not built. Run: cd frontend && npm run build"},
            status_code=503
        )